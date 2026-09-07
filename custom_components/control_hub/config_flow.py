"""Config flow for Control Hub."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_DATABASE_URL,
    CONF_FIRESTORE_PATH,
    CONF_HUB_ID,
    CONF_PAIRING_CODE,
    CONF_PROJECT_ID,
    CONF_REFRESH_TOKEN,
    CONF_RTDB_PATH,
    CONF_SETUP_URL,
    DEFAULT_FIRESTORE_PATH,
    DEFAULT_RTDB_PATH,
    DOMAIN,
)
from .firebase import (
    FirebaseAuthError,
    FirebaseClient,
    FirebaseError,
    redeem_pairing_code,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SETUP_URL): str,
        vol.Required(CONF_PAIRING_CODE): str,
        vol.Optional(CONF_FIRESTORE_PATH, default=DEFAULT_FIRESTORE_PATH): str,
        vol.Optional(CONF_RTDB_PATH, default=DEFAULT_RTDB_PATH): str,
    }
)


class ControlHubConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the pairing-code based config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            try:
                pairing = await redeem_pairing_code(
                    session,
                    user_input[CONF_SETUP_URL],
                    user_input[CONF_PAIRING_CODE],
                )
                client = await FirebaseClient.async_from_custom_token(
                    session,
                    project_id=pairing.project_id,
                    api_key=pairing.api_key,
                    database_url=pairing.database_url,
                    custom_token=pairing.custom_token,
                )
            except FirebaseAuthError:
                errors["base"] = "invalid_code"
            except FirebaseError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(pairing.hub_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Control Hub {pairing.hub_id}",
                    data={
                        CONF_HUB_ID: pairing.hub_id,
                        CONF_PROJECT_ID: pairing.project_id,
                        CONF_API_KEY: pairing.api_key,
                        CONF_DATABASE_URL: pairing.database_url,
                        CONF_REFRESH_TOKEN: client.refresh_token,
                        CONF_FIRESTORE_PATH: user_input[CONF_FIRESTORE_PATH],
                        CONF_RTDB_PATH: user_input[CONF_RTDB_PATH],
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )
