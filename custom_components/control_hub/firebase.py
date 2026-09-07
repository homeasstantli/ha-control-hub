"""Async Firebase client for the Control Hub integration.

Everything here is plain REST against Google APIs so no blocking SDK is pulled
into Home Assistant. It supports:

* Redeeming a one-time pairing code (via a Cloud Function you deploy) into a
  Firebase custom token plus project configuration.
* Exchanging the custom token for an ID token / refresh token.
* Refreshing the ID token when it expires.
* Reading and writing Cloud Firestore documents.
* Reading and writing the Realtime Database.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from aiohttp import ClientResponseError, ClientSession

from .const import (
    FIRESTORE_BASE,
    IDENTITY_TOOLKIT_URL,
    SECURE_TOKEN_URL,
)


class FirebaseAuthError(Exception):
    """Raised when authentication with Firebase fails."""


class FirebaseError(Exception):
    """Raised when a Firebase data request fails."""


@dataclass
class PairingResult:
    """Configuration returned by the pairing Cloud Function."""

    hub_id: str
    project_id: str
    api_key: str
    database_url: str
    custom_token: str
    raw: dict[str, Any] = field(default_factory=dict)


async def redeem_pairing_code(
    session: ClientSession, setup_url: str, pairing_code: str
) -> PairingResult:
    """Exchange a pairing code for a custom token and project config.

    ``setup_url`` is the HTTPS URL of your deployed ``redeemPairingCode`` Cloud
    Function. It must return JSON shaped like::

        {
          "hubId": "...",
          "projectId": "...",
          "apiKey": "...",
          "databaseURL": "https://<project>-default-rtdb.firebaseio.com",
          "token": "<firebase custom token>"
        }
    """
    try:
        async with session.post(
            setup_url,
            json={"code": pairing_code.strip()},
            raise_for_status=True,
        ) as resp:
            payload = await resp.json()
    except ClientResponseError as err:
        raise FirebaseAuthError(f"Pairing failed ({err.status})") from err

    try:
        return PairingResult(
            hub_id=payload["hubId"],
            project_id=payload["projectId"],
            api_key=payload["apiKey"],
            database_url=payload["databaseURL"].rstrip("/"),
            custom_token=payload["token"],
            raw=payload,
        )
    except KeyError as err:
        raise FirebaseAuthError(f"Pairing response missing {err}") from err


class FirebaseClient:
    """Authenticated client bound to a single hub / Firebase project."""

    def __init__(
        self,
        session: ClientSession,
        *,
        project_id: str,
        api_key: str,
        database_url: str,
        refresh_token: str,
    ) -> None:
        self._session = session
        self._project_id = project_id
        self._api_key = api_key
        self._database_url = database_url.rstrip("/")
        self._refresh_token = refresh_token
        self._id_token: str | None = None
        self._expires_at: float = 0.0

    @property
    def refresh_token(self) -> str:
        """Return the current refresh token (persist this in the config entry)."""
        return self._refresh_token

    @classmethod
    async def async_from_custom_token(
        cls,
        session: ClientSession,
        *,
        project_id: str,
        api_key: str,
        database_url: str,
        custom_token: str,
    ) -> "FirebaseClient":
        """Create a client by trading a custom token for a refresh token."""
        try:
            async with session.post(
                IDENTITY_TOOLKIT_URL,
                params={"key": api_key},
                json={"token": custom_token, "returnSecureToken": True},
                raise_for_status=True,
            ) as resp:
                data = await resp.json()
        except ClientResponseError as err:
            raise FirebaseAuthError(
                f"signInWithCustomToken failed ({err.status})"
            ) from err

        client = cls(
            session,
            project_id=project_id,
            api_key=api_key,
            database_url=database_url,
            refresh_token=data["refreshToken"],
        )
        client._id_token = data["idToken"]
        client._expires_at = time.monotonic() + int(data.get("expiresIn", 3600)) - 60
        return client

    async def _async_token(self) -> str:
        """Return a valid ID token, refreshing it if needed."""
        if self._id_token and time.monotonic() < self._expires_at:
            return self._id_token

        try:
            async with self._session.post(
                SECURE_TOKEN_URL,
                params={"key": self._api_key},
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                },
                raise_for_status=True,
            ) as resp:
                data = await resp.json()
        except ClientResponseError as err:
            raise FirebaseAuthError(f"Token refresh failed ({err.status})") from err

        self._id_token = data["id_token"]
        self._refresh_token = data["refresh_token"]
        self._expires_at = time.monotonic() + int(data.get("expires_in", 3600)) - 60
        return self._id_token

    async def async_check_auth(self) -> None:
        """Force a token fetch to validate credentials."""
        await self._async_token()

    # ------------------------------------------------------------------
    # Cloud Firestore
    # ------------------------------------------------------------------
    async def async_get_firestore(self, path: str) -> dict[str, Any]:
        """Read one Firestore document. ``path`` is like ``hubs/abc/config``."""
        token = await self._async_token()
        url = (
            f"{FIRESTORE_BASE}/projects/{self._project_id}"
            f"/databases/(default)/documents/{path.strip('/')}"
        )
        try:
            async with self._session.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                raise_for_status=True,
            ) as resp:
                doc = await resp.json()
        except ClientResponseError as err:
            if err.status == 404:
                return {}
            raise FirebaseError(f"Firestore read failed ({err.status})") from err
        return _decode_firestore_fields(doc.get("fields", {}))

    async def async_set_firestore(self, path: str, data: dict[str, Any]) -> None:
        """Write (merge) a Firestore document."""
        token = await self._async_token()
        base = (
            f"{FIRESTORE_BASE}/projects/{self._project_id}"
            f"/databases/(default)/documents/{path.strip('/')}"
        )
        params = [("updateMask.fieldPaths", key) for key in data]
        body = {"fields": _encode_firestore_fields(data)}
        try:
            async with self._session.patch(
                base,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                json=body,
                raise_for_status=True,
            ):
                pass
        except ClientResponseError as err:
            raise FirebaseError(f"Firestore write failed ({err.status})") from err

    # ------------------------------------------------------------------
    # Realtime Database
    # ------------------------------------------------------------------
    async def async_get_rtdb(self, path: str) -> Any:
        """Read a node from the Realtime Database."""
        token = await self._async_token()
        url = f"{self._database_url}/{path.strip('/')}.json"
        try:
            async with self._session.get(
                url, params={"auth": token}, raise_for_status=True
            ) as resp:
                return await resp.json()
        except ClientResponseError as err:
            raise FirebaseError(f"RTDB read failed ({err.status})") from err

    async def async_set_rtdb(self, path: str, data: Any) -> None:
        """Overwrite a node in the Realtime Database."""
        token = await self._async_token()
        url = f"{self._database_url}/{path.strip('/')}.json"
        try:
            async with self._session.put(
                url, params={"auth": token}, json=data, raise_for_status=True
            ):
                pass
        except ClientResponseError as err:
            raise FirebaseError(f"RTDB write failed ({err.status})") from err

    async def async_push_rtdb(self, path: str, data: Any) -> str:
        """Append a child with a generated key; returns the new key."""
        token = await self._async_token()
        url = f"{self._database_url}/{path.strip('/')}.json"
        try:
            async with self._session.post(
                url, params={"auth": token}, json=data, raise_for_status=True
            ) as resp:
                result = await resp.json()
        except ClientResponseError as err:
            raise FirebaseError(f"RTDB push failed ({err.status})") from err
        return result.get("name", "")


# ----------------------------------------------------------------------
# Minimal Firestore value <-> Python conversion
# ----------------------------------------------------------------------
def _encode_firestore_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {key: _encode_value(value) for key, value in data.items()}


def _encode_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, dict):
        return {"mapValue": {"fields": _encode_firestore_fields(value)}}
    if isinstance(value, (list, tuple)):
        return {"arrayValue": {"values": [_encode_value(item) for item in value]}}
    return {"stringValue": str(value)}


def _decode_firestore_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: _decode_value(value) for key, value in fields.items()}


def _decode_value(value: dict[str, Any]) -> Any:
    if "nullValue" in value:
        return None
    if "booleanValue" in value:
        return value["booleanValue"]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return value["doubleValue"]
    if "stringValue" in value:
        return value["stringValue"]
    if "mapValue" in value:
        return _decode_firestore_fields(value["mapValue"].get("fields", {}))
    if "arrayValue" in value:
        return [_decode_value(item) for item in value["arrayValue"].get("values", [])]
    if "timestampValue" in value:
        return value["timestampValue"]
    return None
