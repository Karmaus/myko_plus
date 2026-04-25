from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MykoApiClient
from .const import CONF_BASE_URL, CONF_EMAIL, CONF_HOME_ID, CONF_PASSWORD, DOMAIN
from .coordinator import MykoDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.LIGHT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = MykoApiClient(async_get_clientsession(hass), entry.data[CONF_BASE_URL])
    api._access_token = entry.data["access_token"]
    api._refresh_token = entry.data.get("refresh_token")
    api._user_id = entry.data.get("user_id")
    api.set_credentials(entry.data.get(CONF_EMAIL), entry.data.get(CONF_PASSWORD))

    def _async_update_tokens(tokens) -> None:
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                "user_id": tokens.user_id,
                "access_token": tokens.access_token,
                "refresh_token": tokens.refresh_token,
            },
        )

    api.set_token_update_callback(_async_update_tokens)

    coordinator = MykoDataUpdateCoordinator(hass, api, entry.data[CONF_HOME_ID])
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
