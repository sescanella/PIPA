"""Tests para agent/preflight.py."""

import json
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config_schema import PIPAConfig
from preflight import (
    check_active_hours,
    acquire_lock,
    release_lock,
    check_internet,
)


def _make_config(**overrides) -> PIPAConfig:
    base = {
        "gmail": {"account": "a@b.com", "whitelist": ["x@y.com"]},
        "owner": {"email": "o@p.com"},
    }
    base.update(overrides)
    return PIPAConfig(**base)


# --- check_active_hours ---

def test_within_active_hours():
    config = _make_config()
    tz = ZoneInfo(config.agent.timezone)
    # Simular 12:00 (dentro de 07:00-22:00)
    fake_now = datetime(2026, 2, 28, 12, 0, 0, tzinfo=tz)
    with patch("preflight.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = check_active_hours(config)
    assert result.passed is True


def test_outside_active_hours():
    config = _make_config()
    tz = ZoneInfo(config.agent.timezone)
    # Simular 23:30 (fuera de 07:00-22:00)
    fake_now = datetime(2026, 2, 28, 23, 30, 0, tzinfo=tz)
    with patch("preflight.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = check_active_hours(config)
    assert result.passed is False
    assert "Fuera de horario" in result.reason


def test_outside_active_hours_early_morning():
    config = _make_config()
    tz = ZoneInfo(config.agent.timezone)
    # Simular 05:00 (antes de 07:00)
    fake_now = datetime(2026, 2, 28, 5, 0, 0, tzinfo=tz)
    with patch("preflight.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = check_active_hours(config)
    assert result.passed is False


# --- acquire_lock ---

@pytest.fixture
def clean_lock(tmp_path):
    """Fixture que patchea get_project_root a tmp_path y limpia el lock."""
    lock_dir = tmp_path / "tmp" / "heartbeat.lock"
    (tmp_path / "tmp").mkdir(parents=True, exist_ok=True)
    with patch("preflight.get_project_root", return_value=tmp_path):
        yield tmp_path, lock_dir
    # Cleanup
    if lock_dir.exists():
        shutil.rmtree(lock_dir)


def test_acquire_lock_success(clean_lock):
    tmp_path, lock_dir = clean_lock
    config = _make_config()
    result = acquire_lock(config)
    assert result.passed is True
    assert lock_dir.exists()
    assert (lock_dir / "info.json").exists()
    # Verificar contenido de info.json
    info = json.loads((lock_dir / "info.json").read_text())
    assert info["pid"] == os.getpid()
    assert "started_at" in info


def test_acquire_lock_already_held(clean_lock):
    """Si otro proceso tiene el lock con PID vivo y < 25 min, falla."""
    tmp_path, lock_dir = clean_lock
    config = _make_config()

    # Crear lock manualmente con PID actual (vivo)
    lock_dir.mkdir(parents=True, exist_ok=True)
    tz = ZoneInfo("America/Santiago")
    info = {
        "pid": os.getpid(),  # PID vivo
        "started_at": datetime.now(tz).isoformat(),
    }
    (lock_dir / "info.json").write_text(json.dumps(info))

    result = acquire_lock(config)
    assert result.passed is False
    assert "Otro ciclo en curso" in result.reason


def test_acquire_lock_stale_pid(clean_lock):
    """Si el PID del lock no existe, lo trata como abandonado y re-adquiere."""
    tmp_path, lock_dir = clean_lock
    config = _make_config()

    # Crear lock con PID inexistente
    lock_dir.mkdir(parents=True, exist_ok=True)
    tz = ZoneInfo("America/Santiago")
    info = {
        "pid": 99999999,  # PID que seguramente no existe
        "started_at": datetime.now(tz).isoformat(),
    }
    (lock_dir / "info.json").write_text(json.dumps(info))

    with patch("preflight._is_pid_alive", return_value=False):
        result = acquire_lock(config)
    assert result.passed is True


def test_acquire_lock_stale_timeout(clean_lock):
    """Si el lock tiene > 25 min, lo trata como stale incluso con PID vivo."""
    tmp_path, lock_dir = clean_lock
    config = _make_config()

    lock_dir.mkdir(parents=True, exist_ok=True)
    tz = ZoneInfo("America/Santiago")
    old_time = datetime.now(tz) - timedelta(minutes=30)
    info = {
        "pid": os.getpid(),
        "started_at": old_time.isoformat(),
    }
    (lock_dir / "info.json").write_text(json.dumps(info))

    result = acquire_lock(config)
    assert result.passed is True


def test_acquire_lock_no_info_json(clean_lock):
    """Lock directory sin info.json — tratar como stale."""
    tmp_path, lock_dir = clean_lock
    config = _make_config()

    lock_dir.mkdir(parents=True, exist_ok=True)
    # No escribir info.json

    result = acquire_lock(config)
    assert result.passed is True


# --- release_lock ---

def test_release_lock(clean_lock):
    tmp_path, lock_dir = clean_lock
    config = _make_config()
    acquire_lock(config)
    assert lock_dir.exists()

    with patch("preflight.get_project_root", return_value=tmp_path):
        release_lock()
    assert not lock_dir.exists()


# --- check_internet ---

def test_internet_success():
    with patch("preflight.urllib.request.urlopen"):
        result = check_internet()
    assert result.passed is True


def test_internet_failure():
    with patch("preflight.urllib.request.urlopen", side_effect=Exception("no net")):
        result = check_internet()
    assert result.passed is False
    assert "internet" in result.reason.lower()
