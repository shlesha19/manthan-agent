
"""
MANTHA — Tool 6: gmail_tool.py
Sends the generated PDF report (and optional inline summary) via Gmail.
Uses Gmail API with OAuth2 credentials.
Robust fallback: SMTP fallback if Gmail API call fails.
"""

import base64
import logging
import os
import smtplib
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [gmail_tool]  %(levelname)s — %(message)s",
)
log = logging.getLogger("gmail_tool")


# ── Config ─────────────────────────────────────────────────────────────────────
# Option A — Gmail API (preferred)
GMAIL_CREDENTIALS_FILE = "credentials.json"   # OAuth2 client secrets file
GMAIL_TOKEN_FILE       = "token.json"         # Auto-generated after first auth

# Option B — SMTP fallback
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = os.getenv("GMAIL_USER", "")           # e.g. mantha@gmail.com
SMTP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")   # Gmail App Password


# ── Gmail API send ─────────────────────────────────────────────────────────────
def _send_via_gmail_api(
    to: list[str],
    subject: str,
    body_html: str,
    attachment_paths: list[str],
    sender: str,
) -> bool:
    """
    Send via the Gmail REST API using google-auth + googleapiclient.
    Returns True on success, False on failure.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
        creds = None

        # Load saved token
        if os.path.exists(GMAIL_TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_FILE, SCOPES)

        # Refresh or re-auth
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    GMAIL_CREDENTIALS_FILE, SCOPES
                )
                creds = flow.run_local_server(port=0)
            with open(GMAIL_TOKEN_FILE, "w") as token:
                token.write(creds.to_json())

        service = build("gmail", "v1", credentials=creds)
        message = _build_mime_message(sender, to, subject, body_html, attachment_paths)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        log.info("Sent via Gmail API → %s", to)
        return True

    except ImportError:
        log.warning("google-auth / googleapiclient not installed. Falling back to SMTP.")
        return False
    except Exception as exc:
        log.warning("Gmail API send failed (%s). Falling back to SMTP.", exc)
        return False


# ── SMTP fallback send ─────────────────────────────────────────────────────────
def _send_via_smtp(
    to: list[str],
    subject: str,
    body_html: str,
    attachment_paths: list[str],
    sender: str,
) -> bool:
    """SMTP fallback using Gmail's TLS port."""
    if not SMTP_USER or not SMTP_PASSWORD:
        log.error(
            "SMTP credentials not set. "
            "Set GMAIL_USER and GMAIL_APP_PASSWORD environment variables."
        )
        return False
    try:
        message = _build_mime_message(sender or SMTP_USER, to, subject, body_html, attachment_paths)
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to, message.as_string())
        log.info("Sent via SMTP → %s", to)
        return True
    except Exception as exc:
        log.error("SMTP send failed: %s", exc)
        return False


# ── MIME message builder ───────────────────────────────────────────────────────
def _build_mime_message(
    sender: str,
    to: list[str],
    subject: str,
    body_html: str,
    attachment_paths: list[str],
) -> MIMEMultipart:
    msg = MIMEMultipart("mixed")
    msg["From"]    = sender
    msg["To"]      = ", ".join(to)
    msg["Subject"] = subject

    # Body
    body_part = MIMEMultipart("alternative")
    body_part.attach(MIMEText(body_html, "html"))
    msg.attach(body_part)

    # Attachments
    for path in attachment_paths:
        if not os.path.exists(path):
            log.warning("Attachment not found, skipping: %s", path)
            continue
        try:
            with open(path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{Path(path).name}"',
            )
            msg.attach(part)
            log.info("Attached: %s", path)
        except Exception as exc:
            log.warning("Could not attach %s: %s", path, exc)

    return msg


# ── Default HTML body ──────────────────────────────────────────────────────────
def _default_body(summary: str, pipeline_name: str = "MANTHA") -> str:
    return f"""
    <html><body style="font-family:Arial,sans-serif;color:#2D2D2D;max-width:640px;margin:auto;">
      <div style="background:#1A1A2E;padding:24px;border-radius:6px 6px 0 0;">
        <h1 style="color:white;margin:0;">{pipeline_name}</h1>
        <p style="color:#AAAACC;margin:6px 0 0;">Automated Data Pipeline Report</p>
      </div>
      <div style="padding:24px;border:1px solid #DDDDDD;border-top:none;border-radius:0 0 6px 6px;">
        <h2 style="color:#4C72B0;">Pipeline Summary</h2>
        <p style="line-height:1.7;">{summary.replace(chr(10), '<br/>')}</p>
        <p style="color:#888888;font-size:12px;margin-top:32px;">
          Full report attached as PDF. This is an automated message from the MANTHA pipeline.
        </p>
      </div>
    </body></html>
    """


# ── Public API ─────────────────────────────────────────────────────────────────
def send_report(
    to: list[str],
    subject:          str  = "MANTHA Pipeline Report",
    summary:          str  = "Please find the latest pipeline report attached.",
    attachment_paths: Optional[list[str]] = None,
    sender:           str  = "",
    body_html:        Optional[str] = None,
) -> bool:
    """
    Send the pipeline report via email.

    Tries Gmail API first; falls back to SMTP automatically.

    Parameters
    ----------
    to               : List of recipient email addresses.
    subject          : Email subject line.
    summary          : Plain-text summary embedded in the HTML body.
    attachment_paths : List of file paths to attach (typically the PDF report).
    sender           : Sender address (used in MIME header; Gmail API uses 'me').
    body_html        : Override the default HTML body entirely.

    Returns
    -------
    True if sent successfully, False otherwise.
    """
    if not to:
        log.error("No recipients provided.")
        return False

    attachments = attachment_paths or []
    html_body   = body_html or _default_body(summary)
    from_addr   = sender or SMTP_USER or "mantha-pipeline@gmail.com"

    log.info("Sending report to %s  |  subject: '%s'  |  attachments: %s",
             to, subject, [Path(p).name for p in attachments])

    # Try Gmail API, then SMTP
    if _send_via_gmail_api(to, subject, html_body, attachments, from_addr):
        return True
    return _send_via_smtp(to, subject, html_body, attachments, from_addr)


# ── Quick smoke-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    success = send_report(
        to=["test@example.com"],
        subject="MANTHA Test Email",
        summary="This is a smoke-test from the MANTHA pipeline. No attachment.",
        attachment_paths=[],
    )
    print("Sent:", success)
