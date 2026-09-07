"""Binary sensor platform for Control Hub."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    async_add_entities([ControlHubConnectivity(coordinator)])


class ControlHubConnectivity(ControlHubEntity, BinarySensorEntity):
    """Whether the last Firebase sync succeeded."""

    _attr_translation_key = "connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: ControlHubCoordinator) -> None:
        super().__init__(coordinator, "connected")

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success
