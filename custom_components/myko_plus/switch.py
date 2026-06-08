from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .climate import _looks_like_climate
from .const import DOMAIN
from .entity_helpers import bool_from_state, extract_device_id, extract_device_name, optimistic_update, state_for_device


class MykoSleepModeSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._device = device
        self._device_id = extract_device_id(device)
        self._attr_unique_id = f"{self._device_id}_sleep_mode"
        self._attr_name = f"{extract_device_name(device)} Sleep Mode"

        from homeassistant.helpers.device_registry import DeviceInfo
        state = device.get("state") or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=extract_device_name(device),
            manufacturer=device.get("client") or device.get("manufacturer"),
            model=device.get("reference") or device.get("model"),
            sw_version=state.get("fwVer"),
            serial_number=device.get("serial_number"),
        )

    @property
    def is_on(self) -> bool | None:
        state = state_for_device(self.coordinator.data.get("states"), self._device_id)
        return bool_from_state(state, "sleepMode")

    async def async_turn_on(self, **kwargs: Any) -> None:
        parameters = {"sleepMode": True}
        await self.coordinator.api.async_update_device_state(self._device_id, parameters)
        optimistic_update(self.coordinator, self._device_id, parameters)

    async def async_turn_off(self, **kwargs: Any) -> None:
        parameters = {"sleepMode": False}
        await self.coordinator.api.async_update_device_state(self._device_id, parameters)
        optimistic_update(self.coordinator, self._device_id, parameters)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime["coordinator"]

    devices = coordinator.data.get("devices", [])
    sleep_switches: list[MykoSleepModeSwitch] = []
    for device in devices:
        if not isinstance(device, dict):
            continue
        if not _looks_like_climate(device):
            continue

        state = device.get("state")
        if isinstance(state, dict) and "sleepMode" in state and extract_device_id(device):
            sleep_switches.append(MykoSleepModeSwitch(coordinator, device))

    async_add_entities(sleep_switches)
