from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .climate import _looks_like_climate
from .const import DOMAIN
from .entity_helpers import (
    build_device_info,
    bool_from_state,
    device_for_device,
    extract_device_id,
    extract_device_name,
    optimistic_update,
    state_for_device,
)


def _looks_like_plug(device: dict[str, Any]) -> bool:
    state = device.get("state") or {}

    if isinstance(state, dict):
        if state.get("deviceName") in ("PLUG", "PLUG_EM"):
            return True

    if device.get("profile_name") in ("PLUG", "PLUG_EM"):
        return True
    if device.get("model") in ("PLUG", "PLUG_EM"):
        return True

    return False


class MykoPlugSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._device = device
        self._device_id = extract_device_id(device)
        self._attr_unique_id = self._device_id
        self._attr_name = extract_device_name(device) or self._device_id
        self._attr_device_info = build_device_info(DOMAIN, self._device_id, device, self._attr_name)

    @property
    def available(self) -> bool:
        device = device_for_device(self.coordinator.data.get("devices"), self._device_id)
        connected = device.get("connected")
        if isinstance(connected, bool):
            return connected
        return super().available

    @property
    def is_on(self) -> bool | None:
        state = state_for_device(self.coordinator.data.get("states"), self._device_id)
        return bool_from_state(state, "power", "isOn", "on", "state")

    async def async_turn_on(self, **kwargs: Any) -> None:
        parameters = {"power": True}
        await self.coordinator.api.async_update_device_state(self._device_id, parameters)
        optimistic_update(self.coordinator, self._device_id, parameters)

    async def async_turn_off(self, **kwargs: Any) -> None:
        parameters = {"power": False}
        await self.coordinator.api.async_update_device_state(self._device_id, parameters)
        optimistic_update(self.coordinator, self._device_id, parameters)


class MykoSleepModeSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._device = device
        self._device_id = extract_device_id(device)
        self._attr_unique_id = f"{self._device_id}_sleep_mode"
        self._attr_name = f"{extract_device_name(device)} Sleep Mode"
        self._attr_device_info = build_device_info(DOMAIN, self._device_id, device, extract_device_name(device))

    @property
    def available(self) -> bool:
        device = device_for_device(self.coordinator.data.get("devices"), self._device_id)
        connected = device.get("connected")
        if isinstance(connected, bool):
            return connected
        return super().available

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
    switches: list[SwitchEntity] = []
    for device in devices:
        if not isinstance(device, dict):
            continue

        device_id = extract_device_id(device)
        if not device_id:
            continue

        if _looks_like_climate(device):
            state = device.get("state")
            if isinstance(state, dict) and "sleepMode" in state:
                switches.append(MykoSleepModeSwitch(coordinator, device))

        if _looks_like_plug(device):
            switches.append(MykoPlugSwitch(coordinator, device))

    async_add_entities(switches)
