from __future__ import annotations

from typing import Any


def extract_device_id(device: dict[str, Any]) -> str | None:
    for key in ("id", "deviceId", "_id", "uuid", "serialNumber", "deviceSerialNumber", "serial_number"):
        value = device.get(key)
        if value not in (None, ""):
            return str(value)

    for key in ("data", "device", "attributes"):
        nested = device.get(key)
        if isinstance(nested, dict):
            nested_id = extract_device_id(nested)
            if nested_id:
                return nested_id

    return None


def extract_device_name(device: dict[str, Any]) -> str:
    for key in ("name", "deviceName", "homeName", "label", "title"):
        value = device.get(key)
        if isinstance(value, str) and value.strip():
            return value

    for key in ("data", "device", "attributes"):
        nested = device.get(key)
        if isinstance(nested, dict):
            nested_name = extract_device_name(nested)
            if nested_name:
                return nested_name

    return "Myko device"


def state_for_device(states: Any, device_id: str) -> dict[str, Any]:
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


def device_for_device(devices: Any, device_id: str) -> dict[str, Any]:
    if isinstance(devices, list):
        for device in devices:
            if isinstance(device, dict) and extract_device_id(device) == device_id:
                return device
    return {}


def bool_from_state(state: dict[str, Any], *keys: str) -> bool | None:
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


def int_from_state(state: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = state.get(key)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def optimistic_update(coordinator, device_id: str, parameters: dict[str, Any]) -> None:
    data = coordinator.data or {}
    states = dict(data.get("states", {}))
    state = dict(state_for_device(states, device_id))
    state.update(parameters)
    states[device_id] = state

    devices: list[Any] = []
    for device in data.get("devices", []):
        if not isinstance(device, dict) or extract_device_id(device) != device_id:
            devices.append(device)
            continue

        updated_device = dict(device)
        inline_state = dict(updated_device.get("state") or {})
        inline_state.update(parameters)
        updated_device["state"] = inline_state
        devices.append(updated_device)

    coordinator.async_set_updated_data({**data, "devices": devices, "states": states})
