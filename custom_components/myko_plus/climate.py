from __future__ import annotations

from typing import Any

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
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

MYKO_HVAC_MODE_TO_DEVICE = {
    HVACMode.COOL: 0,
    HVACMode.HEAT: 1,
    HVACMode.FAN_ONLY: 2,
    HVACMode.DRY: 3,
}
MYKO_HVAC_MODE_FROM_DEVICE = {value: key for key, value in MYKO_HVAC_MODE_TO_DEVICE.items()}
MYKO_FAN_MODE_TO_DEVICE = {"low": 0, "medium": 1, "high": 2}
MYKO_FAN_MODE_FROM_DEVICE = {value: key for key, value in MYKO_FAN_MODE_TO_DEVICE.items()}
MYKO_SWING_ON = "on"
MYKO_SWING_OFF = "off"
MYKO_TARGET_TEMP_MIN = 16
MYKO_TARGET_TEMP_MAX = 32


def _looks_like_climate(device: dict[str, Any]) -> bool:
    state = device.get("state") or {}

    if isinstance(state, dict):
        if state.get("deviceName") in ("PORTABLE_AC", "AIR_CONDITIONER"):
            return True

    if device.get("profile_name") in ("PORTABLE_AC", "AIR_CONDITIONER"):
        return True
    if device.get("model") in ("PORTABLE_AC", "AIR_CONDITIONER"):
        return True

    return False


class MykoClimate(CoordinatorEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.FAN_ONLY, HVACMode.DRY]
    _attr_fan_modes = list(MYKO_FAN_MODE_TO_DEVICE)
    _attr_swing_modes = [MYKO_SWING_OFF, MYKO_SWING_ON]
    _attr_min_temp = MYKO_TARGET_TEMP_MIN
    _attr_max_temp = MYKO_TARGET_TEMP_MAX

    def __init__(self, coordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._device = device
        self._device_id = extract_device_id(device)
        self._attr_unique_id = self._device_id
        self._attr_name = extract_device_name(device) or self._device_id

    @property
    def available(self) -> bool:
        device = device_for_device(self.coordinator.data.get("devices"), self._device_id)
        connected = device.get("connected")
        if isinstance(connected, bool):
            return connected
        return super().available

    @property
    def current_temperature(self) -> float | None:
        state = state_for_device(self.coordinator.data.get("states"), self._device_id)
        current_temp = int_from_state(state, "currentTemp", "temperature", "currentTemperature")
        return float(current_temp) if current_temp is not None else None

    @property
    def target_temperature(self) -> float | None:
        state = state_for_device(self.coordinator.data.get("states"), self._device_id)
        target_temp = int_from_state(state, "targetTemp", "temperature", "targetTemperature")
        return float(target_temp) if target_temp is not None else None

    @property
    def hvac_mode(self) -> HVACMode:
        state = state_for_device(self.coordinator.data.get("states"), self._device_id)
        if not bool_from_state(state, "power"):
            return HVACMode.OFF

        raw_mode = int_from_state(state, "mode")
        return MYKO_HVAC_MODE_FROM_DEVICE.get(raw_mode, HVACMode.COOL)

    @property
    def hvac_action(self) -> HVACAction | None:
        current_mode = self.hvac_mode
        if current_mode == HVACMode.OFF:
            return HVACAction.OFF
        if current_mode == HVACMode.COOL:
            return HVACAction.COOLING
        if current_mode == HVACMode.HEAT:
            return HVACAction.HEATING
        if current_mode == HVACMode.DRY:
            return HVACAction.DRYING
        if current_mode == HVACMode.FAN_ONLY:
            return HVACAction.FAN
        return None

    @property
    def fan_mode(self) -> str | None:
        state = state_for_device(self.coordinator.data.get("states"), self._device_id)
        raw_speed = int_from_state(state, "fanSpeed")
        return MYKO_FAN_MODE_FROM_DEVICE.get(raw_speed)

    @property
    def swing_mode(self) -> str | None:
        state = state_for_device(self.coordinator.data.get("states"), self._device_id)
        air_swing = bool_from_state(state, "airSwing")
        if air_swing is None:
            return None
        return MYKO_SWING_ON if air_swing else MYKO_SWING_OFF

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        rounded_temperature = max(MYKO_TARGET_TEMP_MIN, min(MYKO_TARGET_TEMP_MAX, round(float(temperature))))
        parameters = {"targetTemp": rounded_temperature}

        if self.hvac_mode == HVACMode.OFF:
            parameters["power"] = True

        await self.coordinator.api.async_update_device_state(self._device_id, parameters)
        optimistic_update(self.coordinator, self._device_id, parameters)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return

        device_mode = MYKO_HVAC_MODE_TO_DEVICE.get(hvac_mode)
        if device_mode is None:
            return

        parameters = {"power": True, "mode": device_mode}
        await self.coordinator.api.async_update_device_state(self._device_id, parameters)
        optimistic_update(self.coordinator, self._device_id, parameters)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        device_speed = MYKO_FAN_MODE_TO_DEVICE.get(fan_mode)
        if device_speed is None:
            return

        parameters = {"fanSpeed": device_speed}
        await self.coordinator.api.async_update_device_state(self._device_id, parameters)
        optimistic_update(self.coordinator, self._device_id, parameters)

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        if swing_mode not in self.swing_modes:
            return

        parameters = {"airSwing": swing_mode == MYKO_SWING_ON}
        await self.coordinator.api.async_update_device_state(self._device_id, parameters)
        optimistic_update(self.coordinator, self._device_id, parameters)

    async def async_turn_on(self) -> None:
        current_mode = self.hvac_mode
        parameters: dict[str, Any] = {"power": True}
        if current_mode not in MYKO_HVAC_MODE_TO_DEVICE:
            parameters["mode"] = MYKO_HVAC_MODE_TO_DEVICE[HVACMode.COOL]

        await self.coordinator.api.async_update_device_state(self._device_id, parameters)
        optimistic_update(self.coordinator, self._device_id, parameters)

    async def async_turn_off(self) -> None:
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
    climates: list[MykoClimate] = []
    for device in devices:
        if not isinstance(device, dict):
            continue
        if _looks_like_climate(device) and extract_device_id(device):
            climates.append(MykoClimate(coordinator, device))

    async_add_entities(climates)
