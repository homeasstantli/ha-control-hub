"""The Control Hub integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    ATTR_DATA,
    ATTR_PATH,
    ATTR_TARGET,
    CONF_API_KEY,
    CONF_DATABASE_URL,
    CONF_FIRESTORE_PATH,
    CONF_HUB_ID,
    CONF_PROJECT_ID,
    CONF_REFRESH_TOKEN,
    CONF_RTDB_PATH,
    DEFAULT_FIRESTORE_PATH,
    DEFAULT_RTDB_PATH,
    DOMAIN,
    SERVICE_PUSH_DATA,
    SERVICE_SET_CONFIG,
)
from .coordinator import ControlHubCoordinator
from .firebase import FirebaseAuthError, FirebaseClient, FirebaseError

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

_SET_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_PATH): cv.string,
        vol.Required(ATTR_DATA): dict,
    }
)
_PUSH_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PATH): cv.string,
        vol.Required(ATTR_DATA): dict,
        vol.Optional(ATTR_TARGET, default="rtdb"): vol.In(["rtdb", "firestore"]),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Control Hub from a config entry."""
    session = async_get_clientsession(hass)
    hub_id = entry.data[CONF_HUB_ID]

    try:
        client = FirebaseClient(
            session,
            project_id=entry.data[CONF_PROJECT_ID],
            api_key=entry.data[CONF_API_KEY],
            database_url=entry.data[CONF_DATABASE_URL],
            refresh_token=entry.data[CONF_REFRESH_TOKEN],
        )
        await client.async_check_auth()
    except FirebaseAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except FirebaseError as err:
        raise ConfigEntryNotReady(str(err)) from err

    firestore_path = entry.data.get(
        CONF_FIRESTORE_PATH, DEFAULT_FIRESTORE_PATH
    ).format(hub_id=hub_id)
    rtdb_path = entry.data.get(CONF_RTDB_PATH, DEFAULT_RTDB_PATH).format(hub_id=hub_id)

    coordinator = ControlHubCoordinator(
        hass, entry, client, firestore_path, rtdb_path
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SET_CONFIG)
            hass.services.async_remove(DOMAIN, SERVICE_PUSH_DATA)
    return unloaded


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_CONFIG):
        return

    def _coordinators() -> list[ControlHubCoordinator]:
        return list(hass.data.get(DOMAIN, {}).values())

    async def _handle_set_config(call: ServiceCall) -> None:
        path = call.data.get(ATTR_PATH)
        for coordinator in _coordinators():
            target = path or coordinator.firestore_path
            await coordinator.client.async_set_firestore(target, call.data[ATTR_DATA])
        await _refresh_all()

    async def _handle_push_data(call: ServiceCall) -> None:
        path = call.data[ATTR_PATH]
        for coordinator in _coordinators():
            if call.data[ATTR_TARGET] == "firestore":
                await coordinator.client.async_set_firestore(path, call.data[ATTR_DATA])
            else:
                await coordinator.client.async_push_rtdb(path, call.data[ATTR_DATA])
        await _refresh_all()

    async def _refresh_all() -> None:
        for coordinator in _coordinators():
            await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_SET_CONFIG, _handle_set_config, schema=_SET_CONFIG_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_PUSH_DATA, _handle_push_data, schema=_PUSH_DATA_SCHEMA
    )
