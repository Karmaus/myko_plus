from __future__ import annotations

from typing import Any

import logging

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .entity_helpers import (
    bool_from_state,
    extract_device_id,
    extract_device_name,
    int_from_state,
    optimistic_update,
    state_for_device,
)

_LOGGER = logging.getLogger(__name__)

MYKO_HVAC_MODE_TO_DEVICE = {
    HVACMode.COOL: 0,
    HVACMode.DRY: 1,
    HVACMode.FAN_ONLY: 2,
    HVACMode.HEAT: 3,
}
MYKO_HVAC_MODE_FROM_DEVICE = {value: key for key, value in MYKO_HVAC_MODE_TO_DEVICE.items()}
MYKO_FAN_MODE_TO_DEVICE = {"low": 0, "medium": 1, "high": 2, "auto": 3}
MYKO_FAN_MODE_FROM_DEVICE = {value: key for key, value in MYKO_FAN_MODE_TO_DEVICE.items()}
MYKO_SWING_ON = "on"
MYKO_SWING_OFF = "off"
MYKO_VERTICAL_SWING_ON = "on"
MYKO_VERTICAL_SWING_OFF = "off"
MYKO_TARGET_TEMP_MIN = 16
MYKO_TARGET_TEMP_MAX = 32
MYKO_PRESET_MODES = ["eco", "turbo", "sleep"]
MYKO_PRESET_TO_DEVICE = {
    "eco": "eco",
    "turbo": "turbo",
    "sleep": "sleep",
}


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
        | ClimateEntityFeature.PRESET_MODE
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.FAN_ONLY, HVACMode.DRY]
    _attr_fan_modes = list(MYKO_FAN_MODE_TO_DEVICE)
    _attr_swing_modes = [MYKO_SWING_OFF, MYKO_SWING_ON]
    _attr_min_temp = MYKO_TARGET_TEMP_MIN
    _attr_max_temp = MYKO_TARGET_TEMP_MAX
    _attr_preset_modes = MYKO_PRESET_MODES + ["none"]

    def __init__(self, coordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._device = device
        self._device_id = extract_device_id(device)
        self._attr_unique_id = self._device_id
        self._attr_name = extract_device_name(device) or self._device_id
        self._preset_mode_state: str | None = None

        from homeassistant.helpers.device_registry import DeviceInfo
        state = device.get("state") or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=self._attr_name,
            manufacturer=device.get("client") or device.get("manufacturer"),
            model=device.get("reference") or device.get("model"),
            sw_version=state.get("fwVer"),
            serial_number=device.get("serial_number"),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        state = state_for_device(self.coordinator.data.get("states"), self._device_id)
        attrs: dict[str, Any] = {}

        # Humidity
        humidity = int_from_state(state, "humidity", "currentHumidity", "indoorHumidity")
        if humidity is not None:
            attrs["current_humidity"] = humidity

        target_humidity = int_from_state(state, "targetHumidity", "dehumidifyLevel")
        if target_humidity is not None:
            attrs["target_humidity"] = target_humidity

        # Vertical swing
        vertical_swing = bool_from_state(state, "verticalSwing", "vSwing", "airSwingVertical")
        if vertical_swing is not None:
            attrs["vertical_swing"] = MYKO_VERTICAL_SWING_ON if vertical_swing else MYKO_VERTICAL_SWING_OFF

        # Sleep mode
        sleep_mode = bool_from_state(state, "sleep", "sleepMode")
        if sleep_mode is not None:
            attrs["sleep_mode"] = sleep_mode

        # Turbo/boost mode
        turbo_mode = bool_from_state(state, "turbo", "boost", "powerful")
        if turbo_mode is not None:
            attrs["turbo_mode"] = turbo_mode

        # Eco mode
        eco_mode = bool_from_state(state, "eco", "ecoMode")
        if eco_mode is not None:
            attrs["eco_mode"] = eco_mode

        # Filter life indicator
        filter_life = int_from_state(state, "filterLife", "filterHours")
        if filter_life is not None:
            attrs["filter_life_hours"] = filter_life

        return attrs

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        state = state_for_device(self.coordinator.data.get("states"), self._device_id)

        # Check for sleep mode
        if bool_from_state(state, "sleep", "sleepMode"):
            return "sleep"

        # Check for turbo/boost mode
        if bool_from_state(state, "turbo", "boost", "powerful"):
            return "turbo"

        # Check for eco mode
        if bool_from_state(state, "eco", "ecoMode"):
            return "eco"

        return "none"

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

        raw_mode = int_from_state(state, "mode", "operationMode", "opMode", "acMode")
        if raw_mode is None:
            mode_str = state.get("mode", "").lower() if isinstance(state.get("mode"), str) else ""
            if "cool" in mode_str:
                return HVACMode.COOL
            elif "heat" in mode_str:
                return HVACMode.HEAT
            elif "fan" in mode_str:
                return HVACMode.FAN_ONLY
            elif "dry" in mode_str or "dehumidif" in mode_str:
                return HVACMode.DRY
            return HVACMode.COOL  # default

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
        raw_speed = int_from_state(state, "fanSpeed", "speed", "windSpeed", "fanLevel")
        if raw_speed is None:
            return None
        return MYKO_FAN_MODE_FROM_DEVICE.get(raw_speed)

    @property
    def swing_mode(self) -> str | None:
        state = state_for_device(self.coordinator.data.get("states"), self._device_id)
        air_swing = bool_from_state(state, "airSwing", "swing", "horizontalSwing", "hSwing")
        if air_swing is None:
            return None
        return MYKO_SWING_ON if air_swing else MYKO_SWING_OFF

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        try:
            rounded_temperature = max(MYKO_TARGET_TEMP_MIN, min(MYKO_TARGET_TEMP_MAX, round(float(temperature) * 2) / 2))
            parameters = {"targetTemp": rounded_temperature}

            if self.hvac_mode == HVACMode.OFF:
                parameters["power"] = True

            _LOGGER.debug("Setting temperature to %s for device %s", rounded_temperature, self._device_id)
            await self.coordinator.api.async_update_device_state(self._device_id, parameters)
            optimistic_update(self.coordinator, self._device_id, parameters)
        except Exception as exc:
            _LOGGER.error("Failed to set temperature for %s: %s", self._device_id, exc)
            raise

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        try:
            if hvac_mode == HVACMode.OFF:
                await self.async_turn_off()
                return

            device_mode = MYKO_HVAC_MODE_TO_DEVICE.get(hvac_mode)
            if device_mode is None:
                return

            parameters = {"power": True, "mode": device_mode}
            _LOGGER.debug("Setting HVAC mode to %s for device %s", hvac_mode, self._device_id)
            await self.coordinator.api.async_update_device_state(self._device_id, parameters)
            optimistic_update(self.coordinator, self._device_id, parameters)
        except Exception as exc:
            _LOGGER.error("Failed to set HVAC mode for %s: %s", self._device_id, exc)
            raise

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        try:
            device_speed = MYKO_FAN_MODE_TO_DEVICE.get(fan_mode)
            if device_speed is None:
                return

            parameters = {"fanSpeed": device_speed}
            _LOGGER.debug("Setting fan mode to %s for device %s", fan_mode, self._device_id)
            await self.coordinator.api.async_update_device_state(self._device_id, parameters)
            optimistic_update(self.coordinator, self._device_id, parameters)
        except Exception as exc:
            _LOGGER.error("Failed to set fan mode for %s: %s", self._device_id, exc)
            raise

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        try:
            if swing_mode not in self.swing_modes:
                return

            parameters = {"airSwing": swing_mode == MYKO_SWING_ON}
            _LOGGER.debug("Setting swing mode to %s for device %s", swing_mode, self._device_id)
            await self.coordinator.api.async_update_device_state(self._device_id, parameters)
            optimistic_update(self.coordinator, self._device_id, parameters)
        except Exception as exc:
            _LOGGER.error("Failed to set swing mode for %s: %s", self._device_id, exc)
            raise

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode."""
        try:
            if preset_mode == "none":
                # Disable all preset modes
                parameters = {"sleep": False, "turbo": False, "eco": False}
            elif preset_mode == "sleep":
                parameters = {"sleep": True, "turbo": False, "eco": False}
            elif preset_mode == "turbo":
                parameters = {"sleep": False, "turbo": True, "eco": False}
            elif preset_mode == "eco":
                parameters = {"sleep": False, "turbo": False, "eco": True}
            else:
                return

            _LOGGER.debug("Setting preset mode to %s for device %s", preset_mode, self._device_id)
            await self.coordinator.api.async_update_device_state(self._device_id, parameters)
            optimistic_update(self.coordinator, self._device_id, parameters)
        except Exception as exc:
            _LOGGER.error("Failed to set preset mode for %s: %s", self._device_id, exc)
            raise

    async def async_turn_on(self) -> None:
        try:
            current_mode = self.hvac_mode
            parameters: dict[str, Any] = {"power": True}
            if current_mode not in MYKO_HVAC_MODE_TO_DEVICE:
                parameters["mode"] = MYKO_HVAC_MODE_TO_DEVICE[HVACMode.COOL]

            _LOGGER.debug("Turning on device %s", self._device_id)
            await self.coordinator.api.async_update_device_state(self._device_id, parameters)
            optimistic_update(self.coordinator, self._device_id, parameters)
        except Exception as exc:
            _LOGGER.error("Failed to turn on device %s: %s", self._device_id, exc)
            raise

    async def async_turn_off(self) -> None:
        try:
            _LOGGER.debug("Turning off device %s", self._device_id)
            await self.coordinator.api.async_turn_off(self._device_id)
            optimistic_update(self.coordinator, self._device_id, {"power": False})
        except Exception as exc:
            _LOGGER.error("Failed to turn off device %s: %s", self._device_id, exc)
            raise

    async def async_update(self) -> None:
        """Manually trigger an update from the device."""
        _LOGGER.debug("Manual update requested for device %s", self._device_id)
        await self.coordinator.async_request_refresh()


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
