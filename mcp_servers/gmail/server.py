"""PIPA Gmail MCP Server — 5 tools for Gmail operations.

Provides: search, get_message, get_attachment, send_reply, modify_labels.
Designed for PIPA v1 agent. See docs/v1-spec.md §11.3.

Logging goes to stderr (stdout reserved for JSON-RPC / MCP protocol).
"""

import base64
import json
import logging
import mimetypes
import os
import sys
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Logging — stderr only (stdout = MCP JSON-RPC)
# ---------------------------------------------------------------------------
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("pipa-gmail")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
CHARACTER_LIMIT = 25_000

# ---------------------------------------------------------------------------
# OAuth2 — shared token.json with agent/main.py (§11.5)
# ---------------------------------------------------------------------------

def _get_gmail_service():
    """Build and return an authenticated Gmail API service.

    Reads paths from env vars (set via mcp.json):
      GOOGLE_TOKEN_PATH      — path to token.json
      GOOGLE_CREDENTIALS_PATH — path to credentials.json (OAuth client)
      ATTACHMENT_DOWNLOAD_DIR — directory for downloaded attachments
    """
    token_path = os.environ.get("GOOGLE_TOKEN_PATH", "token.json")
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                raise FileNotFoundError(
                    f"credentials.json not found at {creds_path}. "
                    "Download it from Google Cloud Console > APIs & Credentials > OAuth 2.0 Client IDs."
                )
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        # Persist for next run
        with open(token_path, "w") as f:
            f.write(creds.to_json())
        log.info("Token saved to %s", token_path)

    return build("gmail", "v1", credentials=creds)


def _service():
    """Cached Gmail service (created once per process)."""
    if not hasattr(_service, "_instance"):
        _service._instance = _get_gmail_service()
    return _service._instance


def _download_dir() -> Path:
    """Return the attachment download directory (defaults to tmp/)."""
    d = Path(os.environ.get("ATTACHMENT_DOWNLOAD_DIR", "tmp"))
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# FastMCP Server
# ---------------------------------------------------------------------------
mcp = FastMCP("pipa-gmail")


# ---- Tool 1: search -------------------------------------------------------

@mcp.tool(
    annotations={
        "title": "Search Gmail",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
def search(query: str, max_results: int = 20) -> str:
    """Search Gmail messages. Returns list of {id, threadId, snippet}.

    Args:
        query: Gmail search query (same syntax as Gmail search bar).
               Examples: 'from:user@example.com', 'has:attachment filename:pdf',
               'newer_than:1d', 'is:unread'.
        max_results: Maximum number of results to return (1-100, default 20).

    Returns:
        JSON array of messages with id, threadId, and snippet.
        Returns '[]' if no messages match.
    """
    svc = _service()
    try:
        resp = svc.users().messages().list(
            userId="me", q=query, maxResults=min(max_results, 100)
        ).execute()
        messages = resp.get("messages", [])
        if not messages:
            return "[]"

        results = []
        for msg_stub in messages:
            msg = svc.users().messages().get(
                userId="me", id=msg_stub["id"], format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            ).execute()
            snippet = msg.get("snippet", "")
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            results.append({
                "id": msg["id"],
                "threadId": msg["threadId"],
                "snippet": snippet[:200],
                "subject": headers.get("Subject", ""),
                "from": headers.get("From", ""),
                "date": headers.get("Date", ""),
            })

        output = json.dumps(results, ensure_ascii=False, indent=2)
        if len(output) > CHARACTER_LIMIT:
            results = results[: len(results) // 2]
            output = json.dumps(results, ensure_ascii=False, indent=2)
            output += "\n\n[Truncated — use a more specific query or reduce max_results]"
        return output

    except Exception as e:
        log.error("search failed: %s", e)
        return f"Error searching Gmail: {e}"


# ---- Tool 2: get_message ---------------------------------------------------

@mcp.tool(
    annotations={
        "title": "Get Gmail Message",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
def get_message(message_id: str) -> str:
    """Get full message with decoded body, headers, and attachment metadata.

    Args:
        message_id: Gmail message ID (from search results).

    Returns:
        JSON object with: id, threadId, labelIds, headers (dict),
        body_text, body_html, attachments [{attachmentId, filename, mimeType, size}].
    """
    svc = _service()
    try:
        msg = svc.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        body_text = ""
        body_html = ""
        attachments = []

        def _walk_parts(parts):
            nonlocal body_text, body_html
            for part in parts:
                mime = part.get("mimeType", "")
                body_data = part.get("body", {})
                if mime == "text/plain" and body_data.get("data"):
                    body_text += base64.urlsafe_b64decode(body_data["data"]).decode("utf-8", errors="replace")
                elif mime == "text/html" and body_data.get("data"):
                    body_html += base64.urlsafe_b64decode(body_data["data"]).decode("utf-8", errors="replace")
                elif body_data.get("attachmentId"):
                    attachments.append({
                        "attachmentId": body_data["attachmentId"],
                        "filename": part.get("filename", "unknown"),
                        "mimeType": mime,
                        "size": body_data.get("size", 0),
                    })
                if part.get("parts"):
                    _walk_parts(part["parts"])

        payload = msg.get("payload", {})
        if payload.get("parts"):
            _walk_parts(payload["parts"])
        elif payload.get("body", {}).get("data"):
            mime = payload.get("mimeType", "")
            data = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
            if mime == "text/plain":
                body_text = data
            elif mime == "text/html":
                body_html = data

        result = {
            "id": msg["id"],
            "threadId": msg["threadId"],
            "labelIds": msg.get("labelIds", []),
            "headers": {
                "From": headers.get("From", ""),
                "To": headers.get("To", ""),
                "Subject": headers.get("Subject", ""),
                "Date": headers.get("Date", ""),
                "Message-ID": headers.get("Message-ID", ""),
                "In-Reply-To": headers.get("In-Reply-To", ""),
                "References": headers.get("References", ""),
            },
            "body_text": body_text[:CHARACTER_LIMIT],
            "body_html": body_html[:CHARACTER_LIMIT],
            "attachments": attachments,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        log.error("get_message failed: %s", e)
        return f"Error getting message {message_id}: {e}"


# ---- Tool 3: get_attachment ------------------------------------------------

@mcp.tool(
    annotations={
        "title": "Download Gmail Attachment",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
def get_attachment(message_id: str, attachment_id: str, filename: str) -> str:
    """Download attachment to tmp/. Returns absolute file path.

    Args:
        message_id: Gmail message ID.
        attachment_id: Attachment ID (from get_message results).
        filename: Filename to save as (e.g. 'plano-001.pdf').

    Returns:
        Absolute file path where the attachment was saved.
    """
    svc = _service()
    try:
        att = svc.users().messages().attachments().get(
            userId="me", messageId=message_id, id=attachment_id
        ).execute()

        data = base64.urlsafe_b64decode(att["data"])
        dest = _download_dir() / filename
        dest.write_bytes(data)
        log.info("Attachment saved: %s (%d bytes)", dest, len(data))
        return str(dest.resolve())

    except Exception as e:
        log.error("get_attachment failed: %s", e)
        return f"Error downloading attachment: {e}"


# ---- Tool 4: send_reply ---------------------------------------------------

@mcp.tool(
    annotations={
        "title": "Reply in Gmail Thread",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
def send_reply(
    thread_id: str,
    in_reply_to_message_id: str,
    to: str,
    subject: str,
    body_html: str,
    attachment_paths: list[str] | None = None,
) -> str:
    """Reply in thread with HTML body and file attachments. Returns sent message ID.

    Constructs proper threading headers (In-Reply-To, References) so the reply
    stays in the same Gmail thread.

    Args:
        thread_id: Gmail thread ID.
        in_reply_to_message_id: RFC 2822 Message-ID of the message being replied to
                                 (e.g. '<CABx...@mail.gmail.com>'). Get it from
                                 get_message headers['Message-ID'].
        to: Recipient email address.
        subject: Email subject (should start with 'Re: ' for replies).
        body_html: HTML body of the reply.
        attachment_paths: Optional list of absolute file paths to attach.

    Returns:
        The sent message ID on success, or error message on failure.
    """
    svc = _service()
    paths = attachment_paths or []
    try:
        if paths:
            mime_msg = MIMEMultipart()
            mime_msg.attach(MIMEText(body_html, "html", "utf-8"))
            for fpath in paths:
                p = Path(fpath)
                if not p.exists():
                    return f"Error: attachment file not found: {fpath}"
                content_type = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
                maintype, subtype = content_type.split("/", 1)
                att = MIMEBase(maintype, subtype)
                att.set_payload(p.read_bytes())
                encoders.encode_base64(att)
                att.add_header("Content-Disposition", "attachment", filename=p.name)
                mime_msg.attach(att)
        else:
            mime_msg = MIMEText(body_html, "html", "utf-8")

        mime_msg["To"] = to
        mime_msg["Subject"] = subject
        mime_msg["In-Reply-To"] = in_reply_to_message_id
        mime_msg["References"] = in_reply_to_message_id

        raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("ascii")
        sent = svc.users().messages().send(
            userId="me",
            body={"raw": raw, "threadId": thread_id},
        ).execute()

        sent_id = sent.get("id", "unknown")
        log.info("Reply sent: id=%s threadId=%s", sent_id, thread_id)
        return sent_id

    except Exception as e:
        log.error("send_reply failed: %s", e)
        return f"Error sending reply: {e}"


# ---- Tool 5: modify_labels ------------------------------------------------

@mcp.tool(
    annotations={
        "title": "Modify Gmail Labels",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
def modify_labels(
    message_id: str,
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
) -> str:
    """Add/remove labels by name. Resolves label names to IDs automatically.

    Args:
        message_id: Gmail message ID.
        add_labels: Label names to add (e.g. ['PIPA/Procesado']).
                    Creates the label if it doesn't exist.
        remove_labels: Label names to remove (e.g. ['UNREAD']).

    Returns:
        JSON with updated labelIds on success, or error message.
    """
    svc = _service()
    to_add = add_labels or []
    to_remove = remove_labels or []

    if not to_add and not to_remove:
        return "Error: provide at least one of add_labels or remove_labels."

    try:
        # Build name → ID mapping
        labels_resp = svc.users().labels().list(userId="me").execute()
        name_to_id = {lbl["name"]: lbl["id"] for lbl in labels_resp.get("labels", [])}

        add_ids = []
        for name in to_add:
            if name in name_to_id:
                add_ids.append(name_to_id[name])
            else:
                # Create label if it doesn't exist
                new_label = svc.users().labels().create(
                    userId="me",
                    body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
                ).execute()
                add_ids.append(new_label["id"])
                log.info("Created label: %s -> %s", name, new_label["id"])

        remove_ids = []
        for name in to_remove:
            if name in name_to_id:
                remove_ids.append(name_to_id[name])
            else:
                log.warning("Label not found for removal: %s (skipped)", name)

        body = {}
        if add_ids:
            body["addLabelIds"] = add_ids
        if remove_ids:
            body["removeLabelIds"] = remove_ids

        if not body:
            return json.dumps({"message": "No label changes applied (labels not found)."})

        result = svc.users().messages().modify(
            userId="me", id=message_id, body=body
        ).execute()

        return json.dumps({
            "id": result["id"],
            "labelIds": result.get("labelIds", []),
        }, indent=2)

    except Exception as e:
        log.error("modify_labels failed: %s", e)
        return f"Error modifying labels: {e}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="stdio")
