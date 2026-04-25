from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MykoApiClient, MykoAuthError
from .const import CONF_BASE_URL, CONF_EMAIL, CONF_HOME_ID, CONF_PASSWORD, DEFAULT_BASE_URL, DOMAIN


class MykoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            api = MykoApiClient(
                async_get_clientsession(self.hass),
                user_input[CONF_BASE_URL],
            )
            try:
                tokens = await api.login(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
                homes = await api.async_get_homes()
            except MykoAuthError:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                if not homes:
                    errors["base"] = "no_homes"
                else:
                    home = homes[0]
                    home_id = (
                        home.get("id")
                        or home.get("homeId")
                        or home.get("_id")
                        or home.get("uuid")
                    )
                    if not home_id:
                        data = home.get("data")
                        if isinstance(data, dict):
                            home_id = (
                                data.get("id")
                                or data.get("homeId")
                                or data.get("_id")
                                or data.get("uuid")
                            )
                    home_name = home.get("name") or home.get("homeName")
                    if not home_name:
                        data = home.get("data")
                        if isinstance(data, dict):
                            home_name = data.get("name") or data.get("homeName")
                    if not home_name:
                        home_name = home_id or "home"

                    return self.async_create_entry(
                        title=f"Myko+ {home_name}",
                        data={
                            CONF_BASE_URL: user_input[CONF_BASE_URL],
                            CONF_EMAIL: user_input[CONF_EMAIL],
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                            CONF_HOME_ID: str(home_id),
                            "user_id": tokens.user_id,
                            "access_token": tokens.access_token,
                            "refresh_token": tokens.refresh_token,
                        },
                    )

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
