"""Focused plug tests without requiring a running Home Assistant installation."""

import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock


COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "myko_plus"


def load_definitions(filename, names, namespace):
    """Compile selected production definitions with lightweight HA stand-ins."""
    tree = ast.parse((COMPONENT / filename).read_text(encoding="utf-8"))
    nodes = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
    nodes.extend(node for node in tree.body if getattr(node, "name", None) in names)
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    exec(compile(module, str(COMPONENT / filename), "exec"), namespace)


class CoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    @property
    def available(self):
        return self.coordinator.last_update_success


class Entity:
    pass


def definitions():
    namespace = {
        "math": math,
        "DOMAIN": "myko_plus",
        "CoordinatorEntity": CoordinatorEntity,
        "SwitchEntity": Entity,
        "SensorEntity": Entity,
        "DeviceInfo": dict,
    }
    load_definitions("entity_helpers.py", {
        "extract_device_id", "extract_device_name", "build_device_info",
        "state_for_device", "device_for_device", "bool_from_state", "optimistic_update",
    }, namespace)
    load_definitions("switch.py", {"_looks_like_plug", "MykoPlugSwitch"}, namespace)
    load_definitions("sensor.py", {"_looks_like_plug_em", "MykoSensor"}, namespace)
    return namespace


class PlugTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ns = definitions()
        self.device = {"_id": "plug-1", "name": "Plug", "connected": True,
                       "state": {"deviceName": "PLUG_EM", "power": False}}
        self.coordinator = SimpleNamespace(
            data={"devices": [self.device], "states": {"plug-1": self.device["state"]}},
            last_update_success=True,
            api=SimpleNamespace(async_update_device_state=AsyncMock()),
        )
        self.coordinator.async_set_updated_data = Mock(
            side_effect=lambda data: setattr(self.coordinator, "data", data))

    def test_detection(self):
        for kind in ("PLUG", "PLUG_EM"):
            for field in ("profile_name", "model"):
                self.assertTrue(self.ns["_looks_like_plug"]({field: kind}))
            self.assertTrue(self.ns["_looks_like_plug"]({"state": {"deviceName": kind}}))
        self.assertFalse(self.ns["_looks_like_plug"]({"model": "LIGHT_RGB"}))
        self.assertTrue(self.ns["_looks_like_plug_em"](self.device))
        self.assertFalse(self.ns["_looks_like_plug_em"]({"model": "PLUG"}))

    async def test_switch_commands_and_state(self):
        entity = self.ns["MykoPlugSwitch"](self.coordinator, self.device)
        self.assertFalse(entity.is_on)
        await entity.async_turn_on()
        self.coordinator.api.async_update_device_state.assert_awaited_with("plug-1", {"power": True})
        self.assertTrue(entity.is_on)
        await entity.async_turn_off()
        self.coordinator.api.async_update_device_state.assert_awaited_with("plug-1", {"power": False})
        self.assertFalse(entity.is_on)

    def test_availability(self):
        entity = self.ns["MykoPlugSwitch"](self.coordinator, self.device)
        self.assertTrue(entity.available)
        self.device["connected"] = False
        self.assertFalse(entity.available)

    async def test_failed_command_does_not_change_state(self):
        entity = self.ns["MykoPlugSwitch"](self.coordinator, self.device)
        self.coordinator.api.async_update_device_state.side_effect = RuntimeError("API unavailable")
        with self.assertRaises(RuntimeError):
            await entity.async_turn_on()
        self.assertFalse(entity.is_on)
        self.coordinator.async_set_updated_data.assert_not_called()

    def test_numeric_sensor_readings(self):
        sensor = self.ns["MykoSensor"](
            self.coordinator, self.device, "power", "Power", None, None, "W",
            ("currentPower", "power"))
        for state, expected in (
            ({"power": True}, None), ({"power": False}, None),
            ({"power": True, "currentPower": 42.5}, 42.5),
            ({"power": 12}, 12), ({"currentPower": "18.5"}, 18.5),
            ({"currentPower": "unknown"}, None), ({}, None),
            ({"currentPower": "NaN"}, None), ({"currentPower": float("inf")}, None),
        ):
            with self.subTest(state=state):
                self.coordinator.data["states"]["plug-1"] = state
                self.assertEqual(sensor.native_value, expected)


if __name__ == "__main__":
    unittest.main()
