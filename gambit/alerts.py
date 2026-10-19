"""Alerts: post to Microsoft Teams, Slack or Google Chat (incoming webhook), and/or
email, when something needs attention."""

from __future__ import annotations

import json
import urllib.request

from .settings import settings


def webhook_url() -> str:
    return (settings.get("alerts/webhook", "") or "").strip()


def kind(url: str) -> str:
    u = url.lower()
    if "hooks.slack.com" in u:
        return "slack"
    if "chat.googleapis.com" in u:
        return "gchat"
    if any(x in u for x in ("webhook.office.com", "logic.azure.com", "powerautomate",
                            "powerplatform.com", "office365.com")):
        return "teams"
    return "generic"


def payload(url: str, text: str, title: str = "GAMbit") -> dict:
    k = kind(url)
    if k == "teams":
        # Works with Teams "Workflows" webhooks (Adaptive Card) – the old
        # Office 365 connectors also accept this shape.
        return {"type": "message", "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard", "version": "1.4",
                        "body": [{"type": "TextBlock", "text": title, "weight": "Bolder",
                                  "size": "Medium"},
                                 {"type": "TextBlock", "text": text, "wrap": True}]}}]}
    if k in ("slack", "gchat"):
        return {"text": f"*{title}*\n{text}"}
    return {"title": title, "text": text}


def post_webhook(text: str, title: str = "GAMbit", url: str = "") -> None:
    url = url or webhook_url()
    if not url:
        return
    data = json.dumps(payload(url, text, title)).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    from .net import _context
    with urllib.request.urlopen(req, timeout=20, context=_context()) as resp:
        resp.read()


def post_chat(text: str, title: str = "GAMbit", space: str = "", as_user: str = ""):
    """Post into a Google Chat space as a person (GAM `user … create chatmessage`)."""
    from . import google_io
    from .directory import run_gam_text
    from .tools.people import chat_args
    space = space or (settings.get("alerts/chat_space", "") or "")
    as_user = as_user or (settings.get("alerts/chat_user", "") or "") or google_io.admin_email()
    if not space or "@" not in as_user:
        raise RuntimeError("Set the Chat space and who posts it (Settings → Google Sheets "
                           "and email).")
    code, out = run_gam_text(chat_args(space, f"*{title}*\n{text}", as_user), timeout=60)
    if code != 0:
        raise RuntimeError(out.strip().splitlines()[-1] if out.strip() else str(code))


def notify(text: str, title: str = "GAMbit", email: bool = True):
    """Send an alert everywhere it's turned on. Never raises."""
    errors = []
    try:
        post_webhook(text, title)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"webhook: {exc}")
    space = (settings.get("alerts/chat_space", "") or "").strip()
    if space:
        try:
            post_chat(text, title, space)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"chat: {exc}")
    from .integrations import ticketing
    if ticketing.option("alert_tickets", False):
        try:
            if ticketing.configured() and ticketing.can("create"):
                ticketing.create(title, text)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"help desk: {exc}")
    to = (settings.get("alerts/email", "") or "").strip()
    if email and to and settings.get("alerts/email_on", True):
        try:
            from . import google_io
            google_io.send_email(to, title, text)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"email: {exc}")
    return errors


def powershell_post(url: str, text_expr: str, title: str = "GAMbit") -> str:
    """A .cmd line that posts to the webhook from a scheduled job (PowerShell).

    text_expr is plain text that may contain %VAR% batch variables.
    """
    body = json.dumps(payload(url, "__TEXT__", title))
    safe = text_expr.replace('"', "").replace("'", "’")
    body = body.replace('"', '\\"').replace("__TEXT__", safe)
    url_q = url.replace("'", "''").replace("%", "%%")
    return ('powershell -NoProfile -Command "Invoke-RestMethod -Method Post -ContentType '
            f"'application/json' -Uri '{url_q}' -Body '{body}'\" >nul 2>&1")
