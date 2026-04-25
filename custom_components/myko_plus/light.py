from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

MYKO_COLOR_TEMP_PRESETS = (2700, 4000, 5000, 6500)
MYKO_COLOR_MODE_RGB = 1
MYKO_COLOR_MODE_MOOD = 2
MYKO_COLOR_MODE_COLOR_TEMP = 3
MYKO_EFFECTS = {f"Mood {preset}": preset for preset in range(1, 9)}
MYKO_EFFECTS_BY_PRESET = {preset: name for name, preset in MYKO_EFFECTS.items()}


def _extract_device_id(device: dict[str, Any]) -> str | None:
    for key in ("id", "deviceId", "_id", "uuid", "serialNumber", "deviceSerialNumber"):
        value = device.get(key)
        if value not in (None, ""):
            return str(value)

    for key in ("data", "device", "attributes"):
        nested = device.get(key)
        if isinstance(nested, dict):
            nested_id = _extract_device_id(nested)
            if nested_id:
                return nested_id

    return None


def _extract_device_name(device: dict[str, Any]) -> str:
    for key in ("name", "deviceName", "homeName", "label", "title"):
        value = device.get(key)
        if isinstance(value, str) and value.strip():
            return value

    for key in ("data", "device", "attributes"):
        nested = device.get(key)
        if isinstance(nested, dict):
            nested_name = _extract_device_name(nested)
            if nested_name:
                return nested_name

    return "Myko device"


def _looks_like_light(device: dict[str, Any]) -> bool:
    fields: list[str] = []
    for key in ("type", "deviceType", "category", "productType", "model", "name", "deviceName"):
        value = device.get(key)
        if isinstance(value, str):
            fields.append(value.lower())

    for key in ("data", "device", "attributes"):
        nested = device.get(key)
        if isinstance(nested, dict):
            for nested_key in ("type", "deviceType", "category", "productType", "model", "name", "deviceName"):
                value = nested.get(nested_key)
                if isinstance(value, str):
                    fields.append(value.lower())

    haystack = " ".join(fields)
    light_markers = ("light", "bulb", "lamp", "rgb", "white", "cct", "living", "bedroom", "kitchen")
    return any(marker in haystack for marker in light_markers)


def _state_for_device(states: Any, device_id: str) -> dict[str, Any]:
    if isinstance(states, dict):
        if device_id in states and isinstance(states[device_id], dict):
            return states[device_id]
        for key in ("states", "devices", "data", "items"):
            value = states.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and str(item.get("id") or item.get("deviceId")) == device_id:
                        return item
            if isinstance(value, dict) and device_id in value and isinstance(value[device_id], dict):
                return value[device_id]
    elif isinstance(states, list):
        for item in states:
            if isinstance(item, dict) and str(item.get("id") or item.get("deviceId")) == device_id:
                return item
    return {}


def _device_for_device(devices: Any, device_id: str) -> dict[str, Any]:
    if isinstance(devices, list):
        for device in devices:
            if isinstance(device, dict) and _extract_device_id(device) == device_id:
                return device
    return {}


def _bool_from_state(state: dict[str, Any], *keys: str) -> bool | None:
    for key in keys:
        if key in state:
            value = state[key]
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            if isinstance(value, str):
                return value.lower() in {"1", "true", "on", "enabled"}
    return None


def _int_from_state(state: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = state.get(key)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _rgb_from_state(state: dict[str, Any]) -> tuple[int, int, int] | None:
    value = state.get("colorRGB")
    if not isinstance(value, str):
        return None

    value = value.strip().lstrip("#")
    if len(value) != 6:
        return None

    try:
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except ValueError:
        return None


def _hex_from_rgb(rgb: tuple[int, int, int]) -> str:
    red, green, blue = rgb
    return f"#{red:02X}{green:02X}{blue:02X}"


class MykoLight(CoordinatorEntity, LightEntity):
    _attr_has_entity_name = True
    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP, ColorMode.RGB}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = list(MYKO_EFFECTS)
    _attr_min_color_temp_kelvin = 2700
    _attr_max_color_temp_kelvin = 6500

    def __init__(self, coordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._device = device
        self._device_id = _extract_device_id(device)
        self._attr_unique_id = self._device_id
        self._attr_name = _extract_device_name(device) or self._device_id

    @property
    def available(self) -> bool:
        device = _device_for_device(self.coordinator.data.get("devices"), self._device_id)
        connected = device.get("connected")
        if isinstance(connected, bool):
            return connected
        return super().available

    @property
    def is_on(self) -> bool | None:
        state = _state_for_device(self.coordinator.data["states"], self._device_id)
        return _bool_from_state(state, "power", "isOn", "on", "state")

    @property
    def brightness(self) -> int | None:
        state = _state_for_device(self.coordinator.data["states"], self._device_id)
        raw = _int_from_state(state, "brightness", "lightBrightness", "dimmer", "level")
        if raw is None:
            return None
        if 0 <= raw <= 100:
            return round(raw * 255 / 100)
        return max(0, min(raw, 255))

    @property
    def color_mode(self) -> ColorMode | None:
        state = _state_for_device(self.coordinator.data["states"], self._device_id)
        color_mode = _int_from_state(state, "colorMode")
        if color_mode == MYKO_COLOR_MODE_RGB:
            return ColorMode.RGB
        if color_mode == MYKO_COLOR_MODE_COLOR_TEMP:
            return ColorMode.COLOR_TEMP

        if _rgb_from_state(state) is not None:
            return ColorMode.RGB
        if self.color_temp_kelvin is not None:
            return ColorMode.COLOR_TEMP
        return None

    @property
    def color_temp_kelvin(self) -> int | None:
        state = _state_for_device(self.coordinator.data["states"], self._device_id)
        return _int_from_state(state, "temperature", "colorTemperature", "kelvin", "temp")

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        state = _state_for_device(self.coordinator.data["states"], self._device_id)
        return _rgb_from_state(state)

    @property
    def effect(self) -> str | None:
        state = _state_for_device(self.coordinator.data["states"], self._device_id)
        preset = _int_from_state(state, "sequencePreset")
        if preset in MYKO_EFFECTS_BY_PRESET:
            return MYKO_EFFECTS_BY_PRESET[preset]
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        rgb = kwargs.get(ATTR_RGB_COLOR)
        effect = kwargs.get(ATTR_EFFECT)

        parameters: dict[str, Any] = {"power": True}
        if brightness is not None:
            parameters["brightness"] = round(brightness * 100 / 255)

        if rgb is not None:
            parameters["colorRGB"] = _hex_from_rgb(rgb)
            parameters["colorMode"] = MYKO_COLOR_MODE_RGB
        elif kelvin is not None:
            parameters["colorTemperature"] = min(
                MYKO_COLOR_TEMP_PRESETS,
                key=lambda preset: abs(preset - kelvin),
            )
            parameters["colorMode"] = MYKO_COLOR_MODE_COLOR_TEMP
        elif effect is not None and effect in MYKO_EFFECTS:
            parameters["sequencePreset"] = MYKO_EFFECTS[effect]
            parameters["colorMode"] = MYKO_COLOR_MODE_MOOD

        await self.coordinator.api.async_update_device_state(self._device_id, parameters)
        self._optimistic_update(parameters)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.api.async_turn_off(self._device_id)
        self._optimistic_update({"power": False})

    def _optimistic_update(self, parameters: dict[str, Any]) -> None:
        data = self.coordinator.data or {}
        states = dict(data.get("states", {}))
        state = dict(_state_for_device(states, self._device_id))
        state.update(parameters)
        states[self._device_id] = state

        devices = []
        for device in data.get("devices", []):
            if not isinstance(device, dict) or _extract_device_id(device) != self._device_id:
                devices.append(device)
                continue

            updated_device = dict(device)
            inline_state = dict(updated_device.get("state") or {})
            inline_state.update(parameters)
            updated_device["state"] = inline_state
            devices.append(updated_device)

        self.coordinator.async_set_updated_data({**data, "devices": devices, "states": states})


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime["coordinator"]

    devices = coordinator.data.get("devices", [])
    lights: list[MykoLight] = []
    for device in devices:
        if not isinstance(device, dict):
            continue
        if _looks_like_light(device) and _extract_device_id(device):
            lights.append(MykoLight(coordinator, device))

    async_add_entities(lights)
