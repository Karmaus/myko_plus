from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import entity_registry as er
import voluptuous as vol

from .api import MykoApiClient
from .const import CONF_BASE_URL, CONF_EMAIL, CONF_HOME_ID, CONF_PASSWORD, DOMAIN
from .coordinator import MykoDataUpdateCoordinator
from .entity_helpers import int_from_state, state_for_device
from .light import MYKO_EFFECTS_BY_PRESET, MYKO_SPEED_EFFECT_PRESETS

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.CLIMATE, Platform.SWITCH, Platform.SENSOR]
SERVICE_SET_MOOD_SPEED = "set_mood_speed"

_LOGGER = logging.getLogger(__name__)


def _service_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("entity_id"): str,
            vol.Required("speed"): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
        }
    )


async def _async_handle_set_mood_speed(hass: HomeAssistant, call: ServiceCall) -> None:
    entity_id = call.data["entity_id"]
    speed = call.data["speed"]

    entity_entry = er.async_get(hass).async_get(entity_id)
    if entity_entry is None or entity_entry.domain != Platform.LIGHT:
        raise HomeAssistantError(f"Entitatea {entity_id} nu este un bec Myko+ valid.")

    runtime = hass.data.get(DOMAIN, {}).get(entity_entry.config_entry_id)
    if runtime is None:
        raise HomeAssistantError(f"Nu am gasit runtime-ul pentru {entity_id}.")

    coordinator = runtime["coordinator"]
    device_id = entity_entry.unique_id
    state = state_for_device(coordinator.data.get("states"), device_id)
    preset = int_from_state(state, "sequencePreset")

    if preset is None:
        raise HomeAssistantError(f"{entity_id} nu are niciun mood activ.")

    if preset not in MYKO_SPEED_EFFECT_PRESETS:
        effect_name = MYKO_EFFECTS_BY_PRESET.get(preset, f"preset {preset}")
        raise HomeAssistantError(
            f"Viteza este disponibila doar pentru mood-urile animate. Mood-ul curent este {effect_name}."
        )

    await runtime["api"].async_update_device_state(device_id, {"animationSpeed": speed})

    data = coordinator.data or {}
    states = dict(data.get("states", {}))
    updated_state = dict(state_for_device(states, device_id))
    updated_state["animationSpeed"] = speed
    states[device_id] = updated_state

    devices: list[dict] = []
    for device in data.get("devices", []):
        if not isinstance(device, dict) or str(device.get("_id")) != device_id:
            devices.append(device)
            continue

        updated_device = dict(device)
        inline_state = dict(updated_device.get("state") or {})
        inline_state["animationSpeed"] = speed
        updated_device["state"] = inline_state
        devices.append(updated_device)

    coordinator.async_set_updated_data({**data, "devices": devices, "states": states})
    _LOGGER.debug("Myko mood speed updated for %s: %s", device_id, speed)


def _make_set_mood_speed_handler(hass: HomeAssistant):
    async def _handler(call: ServiceCall) -> None:
        await _async_handle_set_mood_speed(hass, call)

    return _handler


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

    if not hass.services.has_service(DOMAIN, SERVICE_SET_MOOD_SPEED):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_MOOD_SPEED,
            _make_set_mood_speed_handler(hass),
            schema=_service_schema(),
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN] and hass.services.has_service(DOMAIN, SERVICE_SET_MOOD_SPEED):
            hass.services.async_remove(DOMAIN, SERVICE_SET_MOOD_SPEED)
    return unload_ok
