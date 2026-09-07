"""Async Firebase client for the Control Hub integration.

No Cloud Functions and no service-account keys: Home Assistant signs in with
Firebase **Anonymous Auth** (free Spark plan) and "claims" a hub key by writing
its anonymous uid into ``hubs/{hub_key}``. Security rules then scope all reads
and writes under ``hubs/{hub_key}/data`` (Firestore) and ``hubs/{hub_key}``
(Realtime Database) to that uid.

The hub key is a long-lived shared secret - treat it like an API token.

Everything here is plain REST against Google APIs so no blocking SDK is pulled
into Home Assistant.
"""

from __future__ import annotations

import time
from typing import Any

from aiohttp import ClientResponseError, ClientSession

from .const import (
    FIRESTORE_BASE,
    SECURE_TOKEN_URL,
    SIGNUP_URL,
)


class FirebaseAuthError(Exception):
    """Raised when authentication with Firebase fails."""


class FirebaseClaimError(Exception):
    """Raised when the hub key cannot be claimed (already owned / invalid)."""


class FirebaseError(Exception):
    """Raised when a Firebase data request fails."""


class FirebaseClient:
    """Anonymous-auth client scoped to a single hub key."""

    def __init__(
        self,
        session: ClientSession,
        *,
        project_id: str,
        api_key: str,
        database_url: str,
        hub_key: str,
        refresh_token: str,
        uid: str | None = None,
    ) -> None:
        self._session = session
        self._project_id = project_id
        self._api_key = api_key
        self._database_url = database_url.rstrip("/")
        self._hub_key = hub_key
        self._refresh_token = refresh_token
        self._uid = uid
        self._id_token: str | None = None
        self._expires_at: float = 0.0

    @property
    def refresh_token(self) -> str:
        """Current refresh token (persist this in the config entry)."""
        return self._refresh_token

    @property
    def uid(self) -> str | None:
        """Anonymous user id this client authenticated as."""
        return self._uid

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    @classmethod
    async def async_sign_in_anonymous(
        cls,
        session: ClientSession,
        *,
        project_id: str,
        api_key: str,
        database_url: str,
        hub_key: str,
    ) -> "FirebaseClient":
        """Create a brand-new anonymous user and return a client for it."""
        try:
            async with session.post(
                SIGNUP_URL,
                params={"key": api_key},
                json={"returnSecureToken": True},
                raise_for_status=True,
            ) as resp:
                data = await resp.json()
        except ClientResponseError as err:
            raise FirebaseAuthError(
                f"Anonymous sign-in failed ({err.status}) - is Anonymous auth "
                "enabled and the API key correct?"
            ) from err

        client = cls(
            session,
            project_id=project_id,
            api_key=api_key,
            database_url=database_url,
            hub_key=hub_key,
            refresh_token=data["refreshToken"],
            uid=data["localId"],
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
        self._uid = data.get("user_id", self._uid)
        self._expires_at = time.monotonic() + int(data.get("expires_in", 3600)) - 60
        return self._id_token

    async def async_check_auth(self) -> None:
        """Force a token fetch to validate credentials."""
        await self._async_token()

    # ------------------------------------------------------------------
    # Claiming the hub key
    # ------------------------------------------------------------------
    async def async_claim(self) -> None:
        """Bind this uid to ``hubs/{hub_key}`` in Firestore and the RTDB.

        Self-provisions the hub document if it does not exist yet. Fails if the
        key is already claimed by a different uid.
        """
        assert self._uid is not None
        await self._async_claim_firestore()
        await self._async_claim_rtdb()

    async def _async_claim_firestore(self) -> None:
        token = await self._async_token()
        doc_url = (
            f"{FIRESTORE_BASE}/projects/{self._project_id}"
            f"/databases/(default)/documents/hubs/{self._hub_key}"
        )
        headers = {"Authorization": f"Bearer {token}"}

        existing: dict[str, Any] | None
        try:
            async with self._session.get(
                doc_url, headers=headers, raise_for_status=True
            ) as resp:
                existing = _decode_firestore_fields((await resp.json()).get("fields", {}))
        except ClientResponseError as err:
            if err.status == 404:
                existing = None
            else:
                raise FirebaseError(f"Firestore read failed ({err.status})") from err

        if existing is not None:
            owner = existing.get("uid")
            if owner and owner != self._uid:
                raise FirebaseClaimError("Hub key is already claimed by another user")
            if existing.get("valid") is False:
                raise FirebaseClaimError("Hub key is marked invalid")
            if owner == self._uid:
                return
            fields = {"uid": self._uid}
        else:
            fields = {"uid": self._uid, "valid": True}

        params = [("updateMask.fieldPaths", key) for key in fields]
        try:
            async with self._session.patch(
                doc_url,
                params=params,
                headers=headers,
                json={"fields": _encode_firestore_fields(fields)},
                raise_for_status=True,
            ):
                pass
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise FirebaseClaimError(
                    "Rules rejected the claim - key may be taken or invalid"
                ) from err
            raise FirebaseError(f"Firestore claim failed ({err.status})") from err

    async def _async_claim_rtdb(self) -> None:
        base = f"{self._database_url}/hubs/{self._hub_key}"
        token = await self._async_token()

        try:
            async with self._session.get(
                f"{base}/uid.json", params={"auth": token}, raise_for_status=True
            ) as resp:
                owner = await resp.json()
        except ClientResponseError as err:
            raise FirebaseError(f"RTDB read failed ({err.status})") from err

        if owner and owner != self._uid:
            raise FirebaseClaimError("Hub key is already claimed by another user")
        if owner == self._uid:
            return

        try:
            async with self._session.put(
                f"{base}/valid.json",
                params={"auth": token},
                json=True,
                raise_for_status=True,
            ):
                pass
            async with self._session.put(
                f"{base}/uid.json",
                params={"auth": token},
                json=self._uid,
                raise_for_status=True,
            ):
                pass
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise FirebaseClaimError(
                    "RTDB rules rejected the claim - key may be taken"
                ) from err
            raise FirebaseError(f"RTDB claim failed ({err.status})") from err

    # ------------------------------------------------------------------
    # Cloud Firestore
    # ------------------------------------------------------------------
    async def async_get_firestore(self, path: str) -> dict[str, Any]:
        """Read one Firestore document. ``path`` like ``hubs/KEY/data/config``."""
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
        try:
            async with self._session.patch(
                base,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                json={"fields": _encode_firestore_fields(data)},
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
