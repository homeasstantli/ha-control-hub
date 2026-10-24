"""HTTP view that exchanges a one-time pairing code for an access token."""

from __future__ import annotations

from http import HTTPStatus

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import CONF_EXPOSED_ENTITIES, DOMAIN, ENTITIES_VIEW_URL, PAIR_VIEW_URL
from .pairing import async_redeem_pairing_code


class ControlHubPairView(HomeAssistantView):
    """POST {"code": "ABCD1234"} -> {"access_token": "..."}.

    Unauthenticated by design (it is the bootstrap). Codes are single-use and
    expire after 5 minutes. Set ``http.cors_allowed_origins`` so the browser
    can call this from your GitHub Pages origin.
    """

    url = PAIR_VIEW_URL
    name = "api:control_hub:pair"
    requires_auth = False

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        try:
            body = await request.json()
        except ValueError:
            return self.json_message("Invalid JSON", HTTPStatus.BAD_REQUEST)

        code = str(body.get("code", "")).strip()
        if not code:
            return self.json_message("Missing code", HTTPStatus.BAD_REQUEST)

        access_token = async_redeem_pairing_code(hass, code)
        if access_token is None:
            return self.json_message(
                "Invalid or expired code", HTTPStatus.UNAUTHORIZED
            )

        return self.json(
            {
                "access_token": access_token,
                "token_type": "Bearer",
                "ha_version": hass.config.as_dict().get("version"),
            }
        )


def _exposed_entity_ids(hass: HomeAssistant) -> set[str] | None:
    """Union of exposed entities across config entries.

    Returns ``None`` if no entry has a filter configured, meaning "expose
    everything" (the original, unfiltered behaviour).
    """
    entries = hass.config_entries.async_entries(DOMAIN)
    configured = [e for e in entries if e.options.get(CONF_EXPOSED_ENTITIES)]
    if not configured:
        return None
    allowed: set[str] = set()
    for entry in configured:
        allowed.update(entry.options[CONF_EXPOSED_ENTITIES])
    return allowed


class ControlHubEntitiesView(HomeAssistantView):
    """GET -> the light/switch states the control website is allowed to see.

    Honors the "exposed entities" picked in Control Hub's Options. If nothing
    has been configured, falls back to every light/switch (same as before
    this filter existed).
    """

    url = ENTITIES_VIEW_URL
    name = "api:control_hub:entities"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        allowed = _exposed_entity_ids(hass)
        states = [
            s.as_dict()
            for s in hass.states.async_all()
            if s.domain in ("light", "switch")
            and (allowed is None or s.entity_id in allowed)
        ]
        return self.json(states)
