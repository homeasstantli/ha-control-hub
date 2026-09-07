"""One-time pairing code -> Home Assistant access token.

Lets a static website (e.g. GitHub Pages) obtain a long-lived access token for
Home Assistant by entering a short code, instead of pasting a raw token.

Flow:

1. User runs the ``control_hub.create_pairing_code`` action in Home Assistant.
   A dedicated non-admin user ("Control Hub Web") is created once, a long-lived
   access token is minted for it, and an 8-character code is returned that maps
   to that token for 5 minutes (single use).
2. The website POSTs ``{"code": "..."}`` to ``/api/control_hub/pair`` and gets
   back ``{"access_token": "..."}``, which it stores locally and uses for
   ``/api/states`` and ``/api/services/...`` calls.
"""

from __future__ import annotations

import secrets
import time
from datetime import timedelta

from homeassistant.auth.const import GROUP_ID_USER
from homeassistant.auth.models import TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DATA_PAIRING_CODES,
    DOMAIN,
    PAIRING_CODE_ALPHABET,
    PAIRING_CODE_LENGTH,
    PAIRING_CODE_TTL,
    WEB_USER_NAME,
    WEB_USER_STORAGE_KEY,
)


async def _async_get_web_user(hass: HomeAssistant):
    """Return the dedicated website user, creating it once and remembering it."""
    store: Store = Store(hass, 1, WEB_USER_STORAGE_KEY)
    data = await store.async_load() or {}
    user_id = data.get("user_id")
    if user_id:
        user = await hass.auth.async_get_user(user_id)
        if user is not None:
            return user

    user = await hass.auth.async_create_user(
        WEB_USER_NAME, group_ids=[GROUP_ID_USER]
    )
    await store.async_save({"user_id": user.id})
    return user


def _prune(codes: dict[str, dict]) -> None:
    now = time.time()
    for code in [c for c, v in codes.items() if v["expires"] < now]:
        codes.pop(code, None)


async def async_create_pairing_code(hass: HomeAssistant) -> dict[str, object]:
    """Mint a long-lived access token and return a short code mapping to it."""
    user = await _async_get_web_user(hass)
    refresh_token = await hass.auth.async_create_refresh_token(
        user,
        client_name=f"Control Hub Web {dt_util.utcnow().isoformat(timespec='seconds')}",
        token_type=TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN,
        access_token_expiration=timedelta(days=3650),
    )
    access_token = hass.auth.async_create_access_token(refresh_token)

    codes: dict[str, dict] = hass.data[DOMAIN].setdefault(DATA_PAIRING_CODES, {})
    _prune(codes)
    code = "".join(
        secrets.choice(PAIRING_CODE_ALPHABET) for _ in range(PAIRING_CODE_LENGTH)
    )
    codes[code] = {
        "access_token": access_token,
        "refresh_token_id": refresh_token.id,
        "expires": time.time() + PAIRING_CODE_TTL,
    }
    return {
        "code": code,
        "expires_in": PAIRING_CODE_TTL,
        "pair_path": "/api/control_hub/pair",
    }


def async_redeem_pairing_code(hass: HomeAssistant, code: str) -> str | None:
    """Return the access token for ``code`` and consume it. None if invalid."""
    codes: dict[str, dict] = hass.data.get(DOMAIN, {}).get(DATA_PAIRING_CODES, {})
    _prune(codes)
    entry = codes.pop(code.strip().upper(), None)
    if entry is None:
        return None
    return entry["access_token"]
