from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MykoApiClient, MykoApiError
from .const import SCAN_INTERVAL_SECONDS
from .entity_helpers import extract_device_id

_LOGGER = logging.getLogger(__name__)


class MykoDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, api: MykoApiClient, home_id: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="myko_plus",
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.api = api
        self.home_id = home_id

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            devices = await self.api.async_get_home_devices(self.home_id)
        except MykoApiError as err:
            raise UpdateFailed(str(err)) from err

        _LOGGER.debug("Myko devices payload for home %s: %s", self.home_id, devices)

        states: dict[str, Any] = {}
        for device in devices:
            if not isinstance(device, dict):
                continue

            device_id = extract_device_id(device) or ""
            if not device_id:
                continue

            # Temporary: log raw device fields so we can see what the API returns
            _LOGGER.warning("Myko raw device fields for %s: %s", device_id, list(device.keys()))
            _LOGGER.warning("Myko raw device data for %s: %s", device_id, device)

            inline_state = device.get("state")
            if isinstance(inline_state, dict):
                states[device_id] = inline_state
                continue

            try:
                states[device_id] = await self.api.async_get_device_state(device_id)
            except MykoApiError as device_err:
                _LOGGER.debug("Device state fetch failed for %s: %s", device_id, device_err)
                states[device_id] = {}

        return {"devices": devices, "states": states}
