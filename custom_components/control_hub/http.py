"""HTTP view that exchanges a one-time pairing code for an access token."""

from __future__ import annotations

from http import HTTPStatus

from aiohttp import web

from homeassistant.components.http import HomeAssistantView

from .const import PAIR_VIEW_URL
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
