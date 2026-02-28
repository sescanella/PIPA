"""Tests para agent/cleanup.py."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cleanup import clean_tmp, purge_processed_emails, run_cleanup


@pytest.fixture
def mock_project(tmp_path):
    """Crea estructura de proyecto falsa en tmp_path."""
    (tmp_path / "tmp").mkdir()
    (tmp_path / "tmp" / ".gitkeep").touch()
    (tmp_path / "state").mkdir()
    with patch("cleanup.get_project_root", return_value=tmp_path):
        yield tmp_path


# --- clean_tmp ---

def test_clean_tmp_removes_files(mock_project):
    tmp_dir = mock_project / "tmp"
    # Crear archivos y directorios temporales
    (tmp_dir / "some_file.pdf").write_text("pdf data")
    (tmp_dir / "crops").mkdir()
    (tmp_dir / "crops" / "region.png").write_text("png data")
    (tmp_dir / "json").mkdir()
    (tmp_dir / "json" / "result.json").write_text("{}")

    removed = clean_tmp()
    assert removed == 3  # some_file.pdf, crops/, json/
    assert (tmp_dir / ".gitkeep").exists()  # Preserved
    assert not (tmp_dir / "some_file.pdf").exists()
    assert not (tmp_dir / "crops").exists()


def test_clean_tmp_preserves_lock(mock_project):
    tmp_dir = mock_project / "tmp"
    lock_dir = tmp_dir / "heartbeat.lock"
    lock_dir.mkdir()
    (lock_dir / "info.json").write_text('{"pid": 1}')

    removed = clean_tmp()
    assert removed == 0
    assert lock_dir.exists()
    assert (lock_dir / "info.json").exists()


def test_clean_tmp_empty(mock_project):
    removed = clean_tmp()
    assert removed == 0


# --- purge_processed_emails ---

def _make_entry(days_ago: int, msg_id: str = "abc123") -> dict:
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {
        "message_id": msg_id,
        "processed_at": ts.isoformat(),
        "sender": "user@example.com",
        "pdfs_count": 1,
        "status": "ok",
    }


def test_purge_old_entries(mock_project):
    state_path = mock_project / "state" / "processed-emails.json"
    data = {
        "processed": [
            _make_entry(5, "recent"),
            _make_entry(45, "old"),
            _make_entry(60, "very_old"),
        ],
        "retention_days": 30,
    }
    state_path.write_text(json.dumps(data))

    purged = purge_processed_emails(retention_days=30)
    assert purged == 2  # old y very_old eliminados

    result = json.loads(state_path.read_text())
    assert len(result["processed"]) == 1
    assert result["processed"][0]["message_id"] == "recent"


def test_purge_nothing_when_all_recent(mock_project):
    state_path = mock_project / "state" / "processed-emails.json"
    data = {
        "processed": [_make_entry(1), _make_entry(10)],
        "retention_days": 30,
    }
    state_path.write_text(json.dumps(data))

    purged = purge_processed_emails()
    assert purged == 0


def test_purge_missing_file(mock_project):
    purged = purge_processed_emails()
    assert purged == 0


def test_purge_empty_processed(mock_project):
    state_path = mock_project / "state" / "processed-emails.json"
    data = {"processed": [], "retention_days": 30}
    state_path.write_text(json.dumps(data))

    purged = purge_processed_emails()
    assert purged == 0


def test_purge_preserves_invalid_timestamps(mock_project):
    state_path = mock_project / "state" / "processed-emails.json"
    data = {
        "processed": [
            {"message_id": "bad", "processed_at": "not-a-date", "sender": "x", "pdfs_count": 1, "status": "ok"},
            _make_entry(45, "old"),
        ],
        "retention_days": 30,
    }
    state_path.write_text(json.dumps(data))

    purged = purge_processed_emails()
    assert purged == 1  # Solo old eliminado, bad preservado
    result = json.loads(state_path.read_text())
    assert len(result["processed"]) == 1
    assert result["processed"][0]["message_id"] == "bad"


# --- run_cleanup ---

def test_run_cleanup_integration(mock_project):
    tmp_dir = mock_project / "tmp"
    (tmp_dir / "temp.pdf").write_text("data")

    state_path = mock_project / "state" / "processed-emails.json"
    data = {
        "processed": [_make_entry(45, "old")],
        "retention_days": 30,
    }
    state_path.write_text(json.dumps(data))

    result = run_cleanup()
    assert result["tmp_removed"] == 1
    assert result["emails_purged"] == 1
