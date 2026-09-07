"""Sensor platform for Control Hub."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ControlHubCoordinator
from .entity import ControlHubEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ControlHubCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ControlHubConfigKeysSensor(coordinator),
            ControlHubLastSyncSensor(coordinator),
        ]
    )


class ControlHubConfigKeysSensor(ControlHubEntity, SensorEntity):
    """Number of keys stored in the hub's Firestore config document."""

    _attr_translation_key = "config_keys"
    _attr_icon = "mdi:cog-outline"

    def __init__(self, coordinator: ControlHubCoordinator) -> None:
        super().__init__(coordinator, "config_keys")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.get("config", {}))

    @property
    def extra_state_attributes(self) -> dict:
        return {"config": self.coordinator.data.get("config", {})}


class ControlHubLastSyncSensor(ControlHubEntity, SensorEntity):
    """Exposes the ``updated`` field from the RTDB state node, if present."""

    _attr_translation_key = "last_sync"
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, coordinator: ControlHubCoordinator) -> None:
        super().__init__(coordinator, "last_sync")

    @property
    def native_value(self) -> str | None:
        state = self.coordinator.data.get("state", {})
        if isinstance(state, dict):
            return state.get("updated")
        return None

    @property
    def extra_state_attributes(self) -> dict:
        state = self.coordinator.data.get("state", {})
        return {"state": state if isinstance(state, dict) else {"value": state}}
