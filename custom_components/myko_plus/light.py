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
from .entity_helpers import (
    bool_from_state,
    device_for_device,
    extract_device_id,
    extract_device_name,
    int_from_state,
    optimistic_update,
    state_for_device,
)

MYKO_COLOR_TEMP_PRESETS = (2700, 4000, 5000, 6500)
MYKO_COLOR_TEMP_TO_DEVICE = {
    2700: 6500,
    4000: 5000,
    5000: 4000,
    6500: 2700,
}
MYKO_COLOR_TEMP_FROM_DEVICE = {value: key for key, value in MYKO_COLOR_TEMP_TO_DEVICE.items()}
MYKO_COLOR_MODE_RGB = 1
MYKO_COLOR_MODE_MOOD = 2
MYKO_COLOR_MODE_COLOR_TEMP = 3
MYKO_EFFECTS = {
    "Flash": 0,
    "Fade 7": 1,
    "Fade 3": 2,
    "Jump 7": 3,
    "Jump 3": 4,
    "Chill": 5,
    "Christmas": 6,
    "Clarity": 7,
    "Dinner party": 8,
    "Focus": 9,
    "Getting ready": 10,
    "Red, White, and Blue": 11,
    "Moonlight": 12,
    "Night Light": 13,
    "Rainbow": 14,
    "Sleep": 15,
    "Valentine's day": 16,
    "Wake Up": 17,
}
MYKO_EFFECTS_BY_PRESET = {preset: name for name, preset in MYKO_EFFECTS.items()}
MYKO_SPEED_EFFECT_PRESETS = {0, 1, 2, 3, 4, 6, 11, 14, 16}


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
        self._device_id = extract_device_id(device)
        self._attr_unique_id = self._device_id
        self._attr_name = extract_device_name(device) or self._device_id

        if device.get("profile_name") == "LIGHT_WHITE":
            self._attr_supported_color_modes = {ColorMode.COLOR_TEMP}
            self._attr_supported_features = 0
            self._attr_effect_list = None

    @property
    def available(self) -> bool:
        device = device_for_device(self.coordinator.data.get("devices"), self._device_id)
        connected = device.get("connected")
        if isinstance(connected, bool):
            return connected
        return super().available

    @property
    def is_on(self) -> bool | None:
        state = state_for_device(self.coordinator.data["states"], self._device_id)
        return bool_from_state(state, "power", "isOn", "on", "state")

    @property
    def brightness(self) -> int | None:
        state = state_for_device(self.coordinator.data["states"], self._device_id)
        raw = int_from_state(state, "brightness", "lightBrightness", "dimmer", "level")
        if raw is None:
            return None
        if 0 <= raw <= 100:
            return round(raw * 255 / 100)
        return max(0, min(raw, 255))

    @property
    def color_mode(self) -> ColorMode | None:
        state = state_for_device(self.coordinator.data["states"], self._device_id)
        color_mode = int_from_state(state, "colorMode")
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
        state = state_for_device(self.coordinator.data["states"], self._device_id)
        raw = int_from_state(state, "temperature", "colorTemperature", "kelvin", "temp")
        if raw is None:
            return None
        return MYKO_COLOR_TEMP_FROM_DEVICE.get(raw, raw)

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        state = state_for_device(self.coordinator.data["states"], self._device_id)
        return _rgb_from_state(state)

    @property
    def effect(self) -> str | None:
        state = state_for_device(self.coordinator.data["states"], self._device_id)
        preset = int_from_state(state, "sequencePreset")
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
            requested_kelvin = min(
                MYKO_COLOR_TEMP_PRESETS,
                key=lambda preset: abs(preset - kelvin),
            )
            parameters["colorTemperature"] = MYKO_COLOR_TEMP_TO_DEVICE.get(
                requested_kelvin,
                requested_kelvin,
            )
            parameters["colorMode"] = MYKO_COLOR_MODE_COLOR_TEMP
        elif effect is not None and effect in MYKO_EFFECTS:
            parameters["sequencePreset"] = MYKO_EFFECTS[effect]
            parameters["colorMode"] = MYKO_COLOR_MODE_MOOD

        await self.coordinator.api.async_update_device_state(self._device_id, parameters)
        optimistic_update(self.coordinator, self._device_id, parameters)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.api.async_turn_off(self._device_id)
        optimistic_update(self.coordinator, self._device_id, {"power": False})


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
        if _looks_like_light(device) and extract_device_id(device):
            lights.append(MykoLight(coordinator, device))

    async_add_entities(lights)
