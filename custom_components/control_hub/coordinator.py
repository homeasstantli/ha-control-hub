"""Data update coordinator for Control Hub."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .firebase import FirebaseClient, FirebaseError

_LOGGER = logging.getLogger(__name__)


class ControlHubCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch the hub's stored config/state from Firestore and the RTDB."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: FirebaseClient,
        firestore_path: str,
        rtdb_path: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({entry.title})",
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.entry = entry
        self.client = client
        self.firestore_path = firestore_path
        self.rtdb_path = rtdb_path

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            config = await self.client.async_get_firestore(self.firestore_path)
            state = await self.client.async_get_rtdb(self.rtdb_path)
        except FirebaseError as err:
            raise UpdateFailed(str(err)) from err

        # Persist any rotated refresh token back into the config entry.
        if self.client.refresh_token != self.entry.data.get("refresh_token"):
            self.hass.config_entries.async_update_entry(
                self.entry,
                data={**self.entry.data, "refresh_token": self.client.refresh_token},
            )

        return {"config": config or {}, "state": state or {}}
