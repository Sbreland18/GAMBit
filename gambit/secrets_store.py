"""Which settings are secrets – API tokens, client secrets, passwords, webhook links – so
they are kept encrypted for this Windows user (DPAPI), never exported in plain text and
always hidden in problem reports. One list, used everywhere."""

from __future__ import annotations

import re

EXACT = {"alerts/webhook", "assistant/api_key", "helpdesk/pin", "iiq/token",
         "oneroster/secret"}
_LAST = {"token", "secret", "password", "api_key", "client_secret", "key", "pin",
         "webhook", "refresh_token", "access_token"}
_PREFIXES = ("ticketing/", "sis_api/", "oneroster/", "iiq/", "assistant/", "alerts/",
             "helpdesk/", "selfservice/", "integrations/")
PREFIX = "enc:v1:"


def is_secret(key: str) -> bool:
    k = (key or "").strip().lower()
    if k in EXACT:
        return True
    if not k.startswith(_PREFIXES):
        return False
    last = k.rsplit("/", 1)[-1]
    return last in _LAST or bool(re.search(r"(secret|token|password|api_?key)$", last))


def seal(value) -> str:
    from .auth import crypto
    if value in (None, "") or not isinstance(value, str) or value.startswith(PREFIX):
        return value
    return PREFIX + crypto.b64(crypto.protect(value.encode("utf-8")))


def unseal(value):
    if not isinstance(value, str) or not value.startswith(PREFIX):
        return value
    from .auth import crypto
    try:
        return crypto.unprotect(crypto.unb64(value[len(PREFIX):])).decode("utf-8")
    except Exception:  # noqa: BLE001 – another user's / PC's secret: treat as not set
        return ""


def migrate(settings) -> int:
    """Encrypt secrets saved in plain text by older versions. Returns how many."""
    n = 0
    for k in settings._s.allKeys():
        if is_secret(k):
            v = settings._s.value(k)
            if isinstance(v, str) and v and not v.startswith(PREFIX):
                settings._s.setValue(k, seal(v))
                n += 1
    if n:
        settings._s.sync()
    return n
