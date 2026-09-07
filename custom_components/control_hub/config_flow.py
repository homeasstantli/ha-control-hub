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
    CONF_HUB_KEY,
    CONF_PROJECT_ID,
    CONF_REFRESH_TOKEN,
    CONF_RTDB_PATH,
    CONF_UID,
    DEFAULT_FIRESTORE_PATH,
    DEFAULT_RTDB_PATH,
    DOMAIN,
    MIN_HUB_KEY_LENGTH,
)
from .firebase import (
    FirebaseAuthError,
    FirebaseClaimError,
    FirebaseClient,
    FirebaseError,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PROJECT_ID): str,
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_DATABASE_URL): str,
        vol.Required(CONF_HUB_KEY): str,
        vol.Optional(CONF_FIRESTORE_PATH, default=DEFAULT_FIRESTORE_PATH): str,
        vol.Optional(CONF_RTDB_PATH, default=DEFAULT_RTDB_PATH): str,
    }
)


class ControlHubConfigFlow(ConfigFlow, domain=DOMAIN):
    """Anonymous-auth + hub-key config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            hub_key = user_input[CONF_HUB_KEY].strip()
            if len(hub_key) < MIN_HUB_KEY_LENGTH:
                errors[CONF_HUB_KEY] = "key_too_short"
            else:
                await self.async_set_unique_id(hub_key)
                self._abort_if_unique_id_configured()
                session = async_get_clientsession(self.hass)
                try:
                    client = await FirebaseClient.async_sign_in_anonymous(
                        session,
                        project_id=user_input[CONF_PROJECT_ID].strip(),
                        api_key=user_input[CONF_API_KEY].strip(),
                        database_url=user_input[CONF_DATABASE_URL].strip(),
                        hub_key=hub_key,
                    )
                    await client.async_claim()
                except FirebaseAuthError:
                    errors["base"] = "invalid_auth"
                except FirebaseClaimError:
                    errors["base"] = "claim_failed"
                except FirebaseError:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title=f"Control Hub ({hub_key})",
                        data={
                            CONF_HUB_KEY: hub_key,
                            CONF_PROJECT_ID: user_input[CONF_PROJECT_ID].strip(),
                            CONF_API_KEY: user_input[CONF_API_KEY].strip(),
                            CONF_DATABASE_URL: user_input[CONF_DATABASE_URL].strip(),
                            CONF_REFRESH_TOKEN: client.refresh_token,
                            CONF_UID: client.uid,
                            CONF_FIRESTORE_PATH: user_input[CONF_FIRESTORE_PATH],
                            CONF_RTDB_PATH: user_input[CONF_RTDB_PATH],
                        },
                    )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )
