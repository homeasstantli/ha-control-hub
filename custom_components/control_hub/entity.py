"""Shared base entity for Control Hub."""

from __future__ import annotations

from homeassistant.helpers.device_info import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ControlHubCoordinator


class ControlHubEntity(CoordinatorEntity[ControlHubCoordinator]):
    """Base entity tying everything to one hub device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ControlHubCoordinator, key: str) -> None:
        super().__init__(coordinator)
        hub_id = coordinator.entry.data["hub_id"]
        self._attr_unique_id = f"{hub_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, hub_id)},
            name=coordinator.entry.title,
            manufacturer="Control Hub",
            model="Firebase-backed hub",
        )
