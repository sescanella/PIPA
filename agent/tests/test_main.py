"""Tests para agent/main.py — Gmail polling (Fase 4)."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import (
    load_gmail_state,
    save_gmail_state,
    load_processed_emails,
    _needs_bootstrap,
    _extract_email_address,
    _has_pdf_attachment,
    _filter_messages,
    _poll_history,
    poll_gmail,
    run_bootstrap,
    write_heartbeat_log,
    write_last_run,
)
from config_schema import PIPAConfig


# --- Helpers ---

def _make_config(**overrides) -> PIPAConfig:
    base = {
        "gmail": {"account": "pipa@gmail.com", "whitelist": ["user@example.com"]},
        "owner": {"email": "owner@example.com"},
    }
    base.update(overrides)
    return PIPAConfig(**base)


def _make_root(tmp_path: Path) -> Path:
    """Create a minimal project root with state/ and logs/ dirs."""
    (tmp_path / "state").mkdir()
    (tmp_path / "logs").mkdir()
    return tmp_path


# --- load_gmail_state ---

def test_load_gmail_state_missing_file(tmp_path):
    root = _make_root(tmp_path)
    state = load_gmail_state(root)
    assert state["last_history_id"] is None
    assert state["bootstrap_completed"] is False


def test_load_gmail_state_valid(tmp_path):
    root = _make_root(tmp_path)
    data = {
        "last_history_id": "12345",
        "last_successful_poll": "2026-02-27T08:00:00-03:00",
        "bootstrap_completed": True,
    }
    (root / "state" / "gmail-state.json").write_text(json.dumps(data))
    state = load_gmail_state(root)
    assert state["last_history_id"] == "12345"
    assert state["bootstrap_completed"] is True


def test_load_gmail_state_invalid_json(tmp_path):
    root = _make_root(tmp_path)
    (root / "state" / "gmail-state.json").write_text("{bad json")
    state = load_gmail_state(root)
    assert state["last_history_id"] is None


# --- save_gmail_state ---

def test_save_gmail_state(tmp_path):
    root = _make_root(tmp_path)
    state = {"last_history_id": "99999", "bootstrap_completed": True}
    save_gmail_state(root, state)
    saved = json.loads((root / "state" / "gmail-state.json").read_text())
    assert saved["last_history_id"] == "99999"


# --- load_processed_emails ---

def test_load_processed_emails_missing(tmp_path):
    root = _make_root(tmp_path)
    result = load_processed_emails(root)
    assert result == set()


def test_load_processed_emails_valid(tmp_path):
    root = _make_root(tmp_path)
    data = {
        "processed": [
            {"message_id": "aaa", "processed_at": "2026-02-27T14:00:00-03:00"},
            {"message_id": "bbb", "processed_at": "2026-02-27T15:00:00-03:00"},
        ]
    }
    (root / "state" / "processed-emails.json").write_text(json.dumps(data))
    result = load_processed_emails(root)
    assert result == {"aaa", "bbb"}


# --- _needs_bootstrap ---

def test_needs_bootstrap_no_state():
    assert _needs_bootstrap({}) is True


def test_needs_bootstrap_not_completed():
    assert _needs_bootstrap({"bootstrap_completed": False, "last_history_id": "123"}) is True


def test_needs_bootstrap_no_history_id():
    assert _needs_bootstrap({"bootstrap_completed": True, "last_history_id": None}) is True


def test_needs_bootstrap_complete():
    assert _needs_bootstrap({"bootstrap_completed": True, "last_history_id": "123"}) is False


# --- _extract_email_address ---

def test_extract_email_with_display_name():
    assert _extract_email_address("John Doe <john@example.com>") == "john@example.com"


def test_extract_email_bare():
    assert _extract_email_address("john@example.com") == "john@example.com"


def test_extract_email_case_insensitive():
    assert _extract_email_address("John@Example.COM") == "john@example.com"


# --- _has_pdf_attachment ---

def test_has_pdf_multipart():
    msg = {
        "payload": {
            "parts": [
                {"mimeType": "text/plain", "body": {"data": "abc"}, "filename": ""},
                {"mimeType": "application/pdf", "body": {"attachmentId": "att1"}, "filename": "plano.pdf"},
            ]
        }
    }
    assert _has_pdf_attachment(msg) is True


def test_has_pdf_no_pdf():
    msg = {
        "payload": {
            "parts": [
                {"mimeType": "text/plain", "body": {"data": "abc"}, "filename": ""},
                {"mimeType": "image/png", "body": {"attachmentId": "att1"}, "filename": "image.png"},
            ]
        }
    }
    assert _has_pdf_attachment(msg) is False


def test_has_pdf_nested_parts():
    msg = {
        "payload": {
            "parts": [
                {
                    "mimeType": "multipart/mixed",
                    "parts": [
                        {"mimeType": "application/pdf", "body": {"attachmentId": "x"}, "filename": "doc.PDF"},
                    ],
                    "filename": "",
                }
            ]
        }
    }
    assert _has_pdf_attachment(msg) is True


def test_has_pdf_single_part_no_pdf():
    msg = {"payload": {"mimeType": "text/plain", "filename": ""}}
    assert _has_pdf_attachment(msg) is False


# --- _poll_history ---

def test_poll_history_single_page():
    service = MagicMock()
    service.users().history().list().execute.return_value = {
        "history": [
            {
                "messagesAdded": [
                    {"message": {"id": "msg1", "threadId": "t1"}},
                    {"message": {"id": "msg2", "threadId": "t2"}},
                ]
            }
        ],
        # No nextPageToken
    }
    result = _poll_history(service, "12345")
    assert set(result) == {"msg1", "msg2"}


def test_poll_history_empty():
    service = MagicMock()
    service.users().history().list().execute.return_value = {}
    result = _poll_history(service, "12345")
    assert result == []


def test_poll_history_deduplicates():
    service = MagicMock()
    service.users().history().list().execute.return_value = {
        "history": [
            {"messagesAdded": [{"message": {"id": "msg1"}}]},
            {"messagesAdded": [{"message": {"id": "msg1"}}]},  # duplicate
        ]
    }
    result = _poll_history(service, "12345")
    assert result == ["msg1"]


# --- _filter_messages ---

def test_filter_whitelist_pass():
    service = MagicMock()
    msg_data = {
        "id": "m1", "threadId": "t1",
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "From", "value": "User <user@example.com>"},
                {"name": "Subject", "value": "Plano"},
            ],
            "parts": [
                {"mimeType": "application/pdf", "body": {"attachmentId": "a1"}, "filename": "plano.pdf"},
            ],
        },
    }
    service.users().messages().get().execute.return_value = msg_data

    result = _filter_messages(service, ["m1"], {"user@example.com"}, set())
    assert len(result) == 1
    assert result[0]["id"] == "m1"


def test_filter_whitelist_reject():
    service = MagicMock()
    msg_data = {
        "id": "m1", "threadId": "t1",
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "From", "value": "stranger@bad.com"},
                {"name": "Subject", "value": "Hey"},
            ],
            "parts": [
                {"mimeType": "application/pdf", "body": {"attachmentId": "a1"}, "filename": "plano.pdf"},
            ],
        },
    }
    service.users().messages().get().execute.return_value = msg_data

    result = _filter_messages(service, ["m1"], {"user@example.com"}, set())
    assert len(result) == 0


def test_filter_no_pdf_reject():
    service = MagicMock()
    msg_data = {
        "id": "m1", "threadId": "t1",
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "From", "value": "user@example.com"},
                {"name": "Subject", "value": "No attachments"},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": "aGVsbG8="}, "filename": ""},
            ],
        },
    }
    service.users().messages().get().execute.return_value = msg_data

    result = _filter_messages(service, ["m1"], {"user@example.com"}, set())
    assert len(result) == 0


def test_filter_already_processed():
    service = MagicMock()
    # Should not even call get() because it's already processed
    result = _filter_messages(service, ["m1"], {"user@example.com"}, {"m1"})
    assert len(result) == 0
    service.users().messages().get.assert_not_called()


# --- write_heartbeat_log ---

def test_write_heartbeat_log(tmp_path):
    root = _make_root(tmp_path)
    tz = ZoneInfo("America/Santiago")
    write_heartbeat_log(root, "OK", tz, emails=0, duration="4s")
    log_content = (root / "logs" / "heartbeat.log").read_text()
    assert "OK" in log_content
    assert "emails=0" in log_content
    assert "duration=4s" in log_content


def test_write_heartbeat_log_append(tmp_path):
    root = _make_root(tmp_path)
    tz = ZoneInfo("America/Santiago")
    write_heartbeat_log(root, "OK", tz, emails=0, duration="1s")
    write_heartbeat_log(root, "WORK", tz, emails=2, duration="120s")
    lines = (root / "logs" / "heartbeat.log").read_text().strip().split("\n")
    assert len(lines) == 2
    assert "OK" in lines[0]
    assert "WORK" in lines[1]


# --- write_last_run ---

def test_write_last_run(tmp_path):
    root = _make_root(tmp_path)
    data = {"timestamp": "2026-02-27T08:00:00-03:00", "result": "OK", "duration_seconds": 4}
    write_last_run(root, data)
    saved = json.loads((root / "state" / "last-run.json").read_text())
    assert saved["result"] == "OK"
    assert saved["duration_seconds"] == 4


# --- poll_gmail integration ---

def test_poll_gmail_bootstrap_trigger(tmp_path):
    """When no gmail-state.json exists, poll_gmail triggers bootstrap."""
    root = _make_root(tmp_path)
    config = _make_config()

    service = MagicMock()
    # getProfile for bootstrap
    service.users().getProfile().execute.return_value = {"historyId": "9999"}
    # search for bootstrap fallback — no results
    service.users().messages().list().execute.return_value = {}

    result = poll_gmail(service, config, root)
    assert result == []

    # State should be persisted
    state = json.loads((root / "state" / "gmail-state.json").read_text())
    assert state["last_history_id"] == "9999"
    assert state["bootstrap_completed"] is True


def test_poll_gmail_no_new_messages(tmp_path):
    """When history returns no new messages, returns empty list."""
    root = _make_root(tmp_path)
    config = _make_config()

    # Pre-seed state
    (root / "state" / "gmail-state.json").write_text(json.dumps({
        "last_history_id": "5000",
        "last_successful_poll": "2026-02-27T08:00:00-03:00",
        "bootstrap_completed": True,
    }))

    service = MagicMock()
    # history.list returns empty
    service.users().history().list().execute.return_value = {}
    # getProfile for fresh historyId
    service.users().getProfile().execute.return_value = {"historyId": "5001"}

    result = poll_gmail(service, config, root)
    assert result == []

    # historyId should be updated
    state = json.loads((root / "state" / "gmail-state.json").read_text())
    assert state["last_history_id"] == "5001"
