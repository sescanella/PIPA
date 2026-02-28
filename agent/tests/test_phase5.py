"""Tests for Phase 5 — Orchestration features in main.py.

Tests for:
- save_processed_email (ADR-006 dedup)
- Consecutive failures tracking (§12.3)
- write_daily_memory
- _run_claude helper
- _get_pdf_attachment_names
- process_email flow
"""

import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

# Add agent/ to path for imports
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import (
    save_processed_email,
    load_processed_emails,
    _load_consecutive_failures,
    _save_consecutive_failures,
    reset_consecutive_failures,
    record_failure_and_maybe_alert,
    write_daily_memory,
    _run_claude,
    _get_pdf_attachment_names,
    _find_claude_binary,
    _ERROR_DESCRIPTIONS,
)
from config_schema import PIPAConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TZ = ZoneInfo("America/Santiago")


@pytest.fixture
def tmp_root(tmp_path):
    """Create a temporary PIPA root directory structure."""
    (tmp_path / "state").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "memory").mkdir()
    (tmp_path / "tmp").mkdir()
    return tmp_path


@pytest.fixture
def config():
    """Create a valid PIPAConfig for testing."""
    return PIPAConfig(
        gmail={"account": "test@gmail.com", "whitelist": ["user@example.com"]},
        owner={"email": "owner@example.com", "alert_consecutive_failures": 3, "alert_cooldown_hours": 24},
        skills={"extract-plano": {"enabled": True, "model": "haiku", "max_turns": 10, "timeout_seconds": 300}},
    )


# ---------------------------------------------------------------------------
# Tests: save_processed_email (ADR-006)
# ---------------------------------------------------------------------------

class TestSaveProcessedEmail:
    def test_creates_new_file(self, tmp_root):
        save_processed_email(tmp_root, "msg123", "user@test.com", 2, "ok", TZ)

        path = tmp_root / "state" / "processed-emails.json"
        assert path.exists()

        with open(path) as f:
            data = json.load(f)

        assert len(data["processed"]) == 1
        entry = data["processed"][0]
        assert entry["message_id"] == "msg123"
        assert entry["sender"] == "user@test.com"
        assert entry["pdfs_count"] == 2
        assert entry["status"] == "ok"
        assert "processed_at" in entry

    def test_appends_to_existing(self, tmp_root):
        # Create initial file
        save_processed_email(tmp_root, "msg1", "a@test.com", 1, "ok", TZ)
        save_processed_email(tmp_root, "msg2", "b@test.com", 3, "partial", TZ)

        with open(tmp_root / "state" / "processed-emails.json") as f:
            data = json.load(f)

        assert len(data["processed"]) == 2
        assert data["processed"][0]["message_id"] == "msg1"
        assert data["processed"][1]["message_id"] == "msg2"

    def test_dedup_check_after_save(self, tmp_root):
        save_processed_email(tmp_root, "msg_dedup", "u@t.com", 1, "ok", TZ)
        processed = load_processed_emails(tmp_root)
        assert "msg_dedup" in processed


# ---------------------------------------------------------------------------
# Tests: Consecutive failures (§12.3)
# ---------------------------------------------------------------------------

class TestConsecutiveFailures:
    def test_load_missing_file(self, tmp_root):
        result = _load_consecutive_failures(tmp_root)
        assert result == {}

    def test_save_and_load(self, tmp_root):
        data = {"error_type": "no_internet", "count": 2}
        _save_consecutive_failures(tmp_root, data)
        loaded = _load_consecutive_failures(tmp_root)
        assert loaded["error_type"] == "no_internet"
        assert loaded["count"] == 2

    def test_reset(self, tmp_root):
        _save_consecutive_failures(tmp_root, {"error_type": "x", "count": 5})
        reset_consecutive_failures(tmp_root)
        loaded = _load_consecutive_failures(tmp_root)
        assert loaded == {}

    def test_increment_same_error(self, tmp_root, config):
        record_failure_and_maybe_alert(tmp_root, config, "no_internet", TZ)
        record_failure_and_maybe_alert(tmp_root, config, "no_internet", TZ)

        loaded = _load_consecutive_failures(tmp_root)
        assert loaded["error_type"] == "no_internet"
        assert loaded["count"] == 2

    def test_reset_on_different_error(self, tmp_root, config):
        record_failure_and_maybe_alert(tmp_root, config, "no_internet", TZ)
        record_failure_and_maybe_alert(tmp_root, config, "no_internet", TZ)
        record_failure_and_maybe_alert(tmp_root, config, "gmail_api_error", TZ)

        loaded = _load_consecutive_failures(tmp_root)
        assert loaded["error_type"] == "gmail_api_error"
        assert loaded["count"] == 1

    @patch("main._send_owner_alert")
    def test_alert_triggered_at_threshold(self, mock_alert, tmp_root, config):
        # 3 consecutive failures should trigger alert
        record_failure_and_maybe_alert(tmp_root, config, "no_internet", TZ)
        record_failure_and_maybe_alert(tmp_root, config, "no_internet", TZ)
        assert not mock_alert.called

        record_failure_and_maybe_alert(tmp_root, config, "no_internet", TZ)
        assert mock_alert.called

    @patch("main._send_owner_alert")
    def test_alert_cooldown_respected(self, mock_alert, tmp_root, config):
        # Set up 3 failures + alert already sent recently
        now = datetime.now(TZ)
        _save_consecutive_failures(tmp_root, {
            "error_type": "no_internet",
            "count": 2,
            "first_failure_at": now.isoformat(),
            "last_failure_at": now.isoformat(),
            "last_alert_sent_at": now.isoformat(),  # Just sent
        })

        # Third failure should NOT re-alert (cooldown not expired)
        record_failure_and_maybe_alert(tmp_root, config, "no_internet", TZ)
        assert not mock_alert.called

    @patch("main._send_owner_alert")
    def test_alert_after_cooldown_expired(self, mock_alert, tmp_root, config):
        now = datetime.now(TZ)
        old_alert = (now - timedelta(hours=25)).isoformat()  # 25h ago > 24h cooldown
        _save_consecutive_failures(tmp_root, {
            "error_type": "no_internet",
            "count": 2,
            "first_failure_at": old_alert,
            "last_failure_at": old_alert,
            "last_alert_sent_at": old_alert,
        })

        record_failure_and_maybe_alert(tmp_root, config, "no_internet", TZ)
        assert mock_alert.called


# ---------------------------------------------------------------------------
# Tests: write_daily_memory
# ---------------------------------------------------------------------------

class TestWriteDailyMemory:
    def test_creates_new_file(self, tmp_root):
        emails = [{
            "from": "user@test.com",
            "subject": "Planos MK-1342",
            "skill_results": [
                {"success": True, "pdf_name": "MK-1342.pdf",
                 "spool_record": {"cajetin": {"ot": "76400-123", "tag_spool": "MK-1342"}}},
                {"success": False, "pdf_name": "corrupto.pdf",
                 "error_detail": "PDF corrupto"},
            ],
        }]

        write_daily_memory(tmp_root, TZ, emails)

        date_str = datetime.now(TZ).strftime("%Y-%m-%d")
        path = tmp_root / "memory" / f"{date_str}.md"
        assert path.exists()

        content = path.read_text()
        assert "user@test.com" in content
        assert "MK-1342.pdf" in content
        assert "OK" in content
        assert "ERROR" in content
        assert "corrupto.pdf" in content

    def test_appends_to_existing(self, tmp_root):
        date_str = datetime.now(TZ).strftime("%Y-%m-%d")
        path = tmp_root / "memory" / f"{date_str}.md"
        path.write_text("# Existing content\n\n")

        write_daily_memory(tmp_root, TZ, [{"from": "a@b.com", "subject": "X", "skill_results": []}])

        content = path.read_text()
        assert "Existing content" in content
        assert "a@b.com" in content


# ---------------------------------------------------------------------------
# Tests: _get_pdf_attachment_names
# ---------------------------------------------------------------------------

class TestGetPdfAttachmentNames:
    def test_multipart_with_pdfs(self):
        msg = {
            "payload": {
                "parts": [
                    {"filename": "doc.pdf", "mimeType": "application/pdf"},
                    {"filename": "image.png", "mimeType": "image/png"},
                    {"filename": "plan.PDF", "mimeType": "application/pdf"},
                ]
            }
        }
        names = _get_pdf_attachment_names(msg)
        assert names == ["doc.pdf", "plan.PDF"]

    def test_no_pdfs(self):
        msg = {"payload": {"parts": [{"filename": "doc.txt", "mimeType": "text/plain"}]}}
        names = _get_pdf_attachment_names(msg)
        assert names == []

    def test_nested_parts(self):
        msg = {
            "payload": {
                "parts": [
                    {
                        "mimeType": "multipart/mixed",
                        "parts": [{"filename": "nested.pdf", "mimeType": "application/pdf"}],
                    }
                ]
            }
        }
        names = _get_pdf_attachment_names(msg)
        assert names == ["nested.pdf"]

    def test_single_part_pdf(self):
        msg = {"payload": {"filename": "single.pdf"}}
        names = _get_pdf_attachment_names(msg)
        assert names == ["single.pdf"]


# ---------------------------------------------------------------------------
# Tests: _run_claude
# ---------------------------------------------------------------------------

class TestRunClaude:
    @patch("main.subprocess.run")
    @patch("main._find_claude_binary", return_value="claude")
    def test_success(self, mock_bin, mock_run, tmp_root):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"emails": [{"message_id": "abc"}]}',
            stderr="",
        )

        result = _run_claude(
            prompt="test",
            root=tmp_root,
            allowed_tools="Read",
            disallowed_tools="Bash",
        )

        assert result["success"] is True
        assert result["result"]["emails"][0]["message_id"] == "abc"

    @patch("main.subprocess.run")
    @patch("main._find_claude_binary", return_value="claude")
    def test_timeout(self, mock_bin, mock_run, tmp_root):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=600)

        result = _run_claude(
            prompt="test",
            root=tmp_root,
            allowed_tools="Read",
            disallowed_tools="Bash",
        )

        assert result["success"] is False
        assert result["error_type"] == "claude_timeout"

    @patch("main.subprocess.run")
    @patch("main._find_claude_binary", return_value="claude")
    def test_nonzero_exit(self, mock_bin, mock_run, tmp_root):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="some error",
        )

        result = _run_claude(
            prompt="test",
            root=tmp_root,
            allowed_tools="Read",
            disallowed_tools="Bash",
        )

        assert result["success"] is False
        assert result["error_type"] == "claude_code_error"

    @patch("main.subprocess.run")
    @patch("main._find_claude_binary", return_value="claude")
    def test_not_found(self, mock_bin, mock_run, tmp_root):
        mock_run.side_effect = FileNotFoundError()

        result = _run_claude(
            prompt="test",
            root=tmp_root,
            allowed_tools="Read",
            disallowed_tools="Bash",
        )

        assert result["success"] is False
        assert result["error_type"] == "claude_code_error"

    @patch("main.subprocess.run")
    @patch("main._find_claude_binary", return_value="claude")
    def test_invalid_json_output(self, mock_bin, mock_run, tmp_root):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="not json at all",
            stderr="",
        )

        result = _run_claude(
            prompt="test",
            root=tmp_root,
            allowed_tools="Read",
            disallowed_tools="Bash",
        )

        assert result["success"] is True
        assert result["result"]["raw_text"] == "not json at all"

    @patch("main.subprocess.run")
    @patch("main._find_claude_binary", return_value="claude")
    def test_empty_stdout(self, mock_bin, mock_run, tmp_root):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        result = _run_claude(
            prompt="test",
            root=tmp_root,
            allowed_tools="Read",
            disallowed_tools="Bash",
        )

        assert result["success"] is False
        assert result["error_type"] == "claude_code_error"

    @patch("main.subprocess.run")
    @patch("main._find_claude_binary", return_value="claude")
    def test_model_and_mcp_config_passed(self, mock_bin, mock_run, tmp_root):
        mock_run.return_value = MagicMock(returncode=0, stdout='{}', stderr="")

        _run_claude(
            prompt="test", root=tmp_root,
            allowed_tools="Read", disallowed_tools="Bash",
            model="haiku", mcp_config="/path/to/mcp.json",
        )

        cmd = mock_run.call_args[0][0]
        assert "--model" in cmd
        assert "haiku" in cmd
        assert "--mcp-config" in cmd
        assert "/path/to/mcp.json" in cmd


# ---------------------------------------------------------------------------
# Tests: Error descriptions/actions completeness
# ---------------------------------------------------------------------------

class TestErrorMappings:
    def test_all_error_types_have_descriptions(self):
        """Ensure all error types from §12.3 have descriptions."""
        expected = [
            "oauth_token_expired", "gmail_mcp_down", "disk_full",
            "claude_code_error", "claude_timeout", "skill_timeout",
            "no_internet", "config_validation_error",
        ]
        for et in expected:
            assert et in _ERROR_DESCRIPTIONS, f"Missing description for {et}"
