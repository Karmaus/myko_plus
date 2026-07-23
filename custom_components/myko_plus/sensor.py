from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .entity_helpers import (
    build_device_info,
    device_for_device,
    extract_device_id,
    extract_device_name,
    state_for_device,
)


def _looks_like_plug_em(device: dict[str, Any]) -> bool:
    state = device.get("state") or {}

    if isinstance(state, dict):
        if state.get("deviceName") == "PLUG_EM":
            return True

    if device.get("profile_name") == "PLUG_EM":
        return True
    if device.get("model") == "PLUG_EM":
        return True

    return False


class MykoSensor(CoordinatorEntity, SensorEntity):
    def __init__(
        self,
        coordinator,
        device: dict[str, Any],
        key_suffix: str,
        name_suffix: str,
        device_class: SensorDeviceClass,
        state_class: SensorStateClass,
        unit: str,
        state_keys: tuple[str, ...],
        divisor: float = 1.0,
    ) -> None:
        super().__init__(coordinator)
        self._device = device
        self._device_id = extract_device_id(device)
        self._key_suffix = key_suffix
        self._state_keys = state_keys
        self._divisor = divisor

        self._attr_unique_id = f"{self._device_id}_{key_suffix}"
        self._attr_name = f"{extract_device_name(device)} {name_suffix}"
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit
        self._attr_device_info = build_device_info(DOMAIN, self._device_id, device, extract_device_name(device))

    @property
    def available(self) -> bool:
        device = device_for_device(self.coordinator.data.get("devices"), self._device_id)
        connected = device.get("connected")
        if isinstance(connected, bool):
            return connected
        return super().available

    @property
    def native_value(self) -> float | int | None:
        state = state_for_device(self.coordinator.data.get("states"), self._device_id)

        # Check all possible keys
        for key in self._state_keys:
            if key in state:
                value = state[key]
                if isinstance(value, (int, float)):
                    return value / self._divisor
                if isinstance(value, str):
                    try:
                        return float(value) / self._divisor
                    except ValueError:
                        pass
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime["coordinator"]

    devices = coordinator.data.get("devices", [])
    sensors: list[SensorEntity] = []
    for device in devices:
        if not isinstance(device, dict):
            continue

        device_id = extract_device_id(device)
        if not device_id:
            continue

        if _looks_like_plug_em(device):
            # Active Power (W)
            sensors.append(
                MykoSensor(
                    coordinator,
                    device,
                    "power",
                    "Power",
                    SensorDeviceClass.POWER,
                    SensorStateClass.MEASUREMENT,
                    UnitOfPower.WATT,
                    ("power", "currentPower", "curPower", "activePower", "current_power", "cur_power"),
                )
            )
            # Total Energy (kWh)
            sensors.append(
                MykoSensor(
                    coordinator,
                    device,
                    "energy",
                    "Energy",
                    SensorDeviceClass.ENERGY,
                    SensorStateClass.TOTAL_INCREASING,
                    UnitOfEnergy.KILO_WATT_HOUR,
                    ("energy", "totalEnergy", "sumEnergy", "kwh", "total_energy", "sum_energy", "totalKwh", "total_kwh"),
                )
            )
            # Voltage (V)
            sensors.append(
                MykoSensor(
                    coordinator,
                    device,
                    "voltage",
                    "Voltage",
                    SensorDeviceClass.VOLTAGE,
                    SensorStateClass.MEASUREMENT,
                    UnitOfElectricPotential.VOLT,
                    ("voltage", "currentVoltage", "curVoltage", "current_voltage", "cur_voltage"),
                )
            )
            # Current (A)
            sensors.append(
                MykoSensor(
                    coordinator,
                    device,
                    "current",
                    "Current",
                    SensorDeviceClass.CURRENT,
                    SensorStateClass.MEASUREMENT,
                    UnitOfElectricCurrent.AMPERE,
                    ("current", "currentCurrent", "curCurrent", "current_current", "cur_current"),
                )
            )

    async_add_entities(sensors)
