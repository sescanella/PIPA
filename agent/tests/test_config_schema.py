"""Tests para agent/config_schema.py."""

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Agregar agent/ al path para imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config_schema import PIPAConfig, load_config, ActiveHours, GmailConfig, OwnerConfig


# --- PIPAConfig ---

def _valid_config() -> dict:
    return {
        "version": "1.0",
        "agent": {
            "name": "PIPA",
            "timezone": "America/Santiago",
            "active_hours": {"start": "07:00", "end": "22:00"},
            "heartbeat_interval_minutes": 30,
        },
        "gmail": {
            "account": "test@gmail.com",
            "whitelist": ["user@example.com"],
        },
        "owner": {
            "email": "owner@example.com",
            "alert_consecutive_failures": 3,
            "alert_cooldown_hours": 24,
        },
        "skills": {
            "extract-plano": {
                "enabled": True,
                "model": "haiku",
                "max_turns": 10,
                "timeout_seconds": 300,
            }
        },
        "email_signature": "-- Test",
    }


def test_valid_config_loads():
    config = PIPAConfig(**_valid_config())
    assert config.agent.name == "PIPA"
    assert config.gmail.account == "test@gmail.com"
    assert config.owner.email == "owner@example.com"
    assert config.skills["extract-plano"].model == "haiku"


def test_defaults_work():
    """Solo gmail y owner son requeridos; el resto tiene defaults."""
    minimal = {
        "gmail": {"account": "a@b.com", "whitelist": ["x@y.com"]},
        "owner": {"email": "o@p.com"},
    }
    config = PIPAConfig(**minimal)
    assert config.version == "1.0"
    assert config.agent.name == "PIPA"
    assert config.agent.active_hours.start == "07:00"
    assert config.agent.heartbeat_interval_minutes == 30
    assert config.skills == {}
    assert config.email_signature == "-- Procesado automaticamente por PIPA v1"


def test_empty_whitelist_raises():
    data = _valid_config()
    data["gmail"]["whitelist"] = []
    with pytest.raises(Exception, match="whitelist no puede estar vacia"):
        PIPAConfig(**data)


def test_invalid_owner_email_raises():
    data = _valid_config()
    data["owner"]["email"] = "not-an-email"
    with pytest.raises(Exception, match="Email invalido"):
        PIPAConfig(**data)


def test_extra_fields_forbidden():
    data = _valid_config()
    data["unknown_field"] = "surprise"
    with pytest.raises(Exception):
        PIPAConfig(**data)


def test_invalid_time_format_raises():
    with pytest.raises(Exception, match="Formato invalido"):
        ActiveHours(start="7:00", end="22:00")


def test_time_out_of_range_raises():
    with pytest.raises(Exception, match="Hora fuera de rango"):
        ActiveHours(start="25:00", end="22:00")


# --- load_config ---

def test_load_config_from_file():
    data = _valid_config()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        f.flush()
        config = load_config(f.name)
    assert config.gmail.account == "test@gmail.com"


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/config.json")


def test_load_config_invalid_json():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{not valid json}")
        f.flush()
        with pytest.raises(json.JSONDecodeError):
            load_config(f.name)
