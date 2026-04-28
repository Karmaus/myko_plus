"""Experimental Myko+ API client built from APK reverse-engineering."""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
import json
import logging
from typing import Any

from aiohttp import ClientResponseError, ClientSession

from .const import DEFAULT_BASE_URL

_LOGGER = logging.getLogger(__name__)


class MykoApiError(Exception):
    """Base API error."""


class MykoAuthError(MykoApiError):
    """Authentication failed."""


@dataclass(slots=True)
class MykoTokens:
    access_token: str
    refresh_token: str | None = None
    user_id: str | None = None


class MykoApiClient:
    """Small async client for the Myko+ cloud."""

    def __init__(self, session: ClientSession, base_url: str = DEFAULT_BASE_URL) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._user_id: str | None = None
        self._email: str | None = None
        self._password: str | None = None
        self._token_update_callback: Callable[[MykoTokens], None] | None = None

    @property
    def user_id(self) -> str | None:
        return self._user_id

    @property
    def access_token(self) -> str | None:
        return self._access_token

    def set_credentials(self, email: str | None, password: str | None) -> None:
        self._email = email
        self._password = password

    def set_token_update_callback(self, callback: Callable[[MykoTokens], None]) -> None:
        self._token_update_callback = callback

    async def login(self, email: str, password: str) -> MykoTokens:
        """Try the most likely login endpoint inferred from the APK.

        This may need adjustment once a live response is captured.
        """
        payload_candidates = [
            {"email": email, "password": password},
            {"username": email, "password": password},
            {"login": email, "password": password},
        ]

        last_error: Exception | None = None
        for payload in payload_candidates:
            try:
                data = await self._request("post", "/v1/auth/login", json=payload, auth=False)
                tokens = self._extract_tokens(data)
                self._apply_tokens(tokens)
                return tokens
            except Exception as err:  # noqa: BLE001
                last_error = err
                _LOGGER.debug("Login candidate failed with payload keys %s: %s", list(payload), err)

        raise MykoAuthError(f"Could not log in to Myko+: {last_error}") from last_error

    async def async_refresh_token(self) -> MykoTokens:
        """Refresh the access token using the mobile app's refresh endpoint."""
        if not self._access_token or not self._refresh_token:
            raise MykoAuthError("No refresh token available")

        data = await self._request(
            "get",
            "/v1/auth/token",
            params={"token": self._access_token, "refresh_token": self._refresh_token},
            auth=False,
            allow_refresh=False,
        )
        tokens = self._extract_tokens(data)
        if not tokens.user_id:
            tokens.user_id = self._user_id
        self._apply_tokens(tokens)
        return tokens

    async def async_reauthenticate(self) -> MykoTokens:
        """Refresh tokens, falling back to full login when credentials are stored."""
        try:
            return await self.async_refresh_token()
        except MykoApiError:
            if self._email and self._password:
                return await self.login(self._email, self._password)
            raise
        except MykoAuthError:
            if self._email and self._password:
                return await self.login(self._email, self._password)
            raise

    async def async_get_homes(self) -> list[dict[str, Any]]:
        self._ensure_authenticated()
        data = await self._request("get", f"/v1/users/{self._user_id}/homes")
        return self._coerce_list(data, preferred_keys=("homes", "items", "data"))

    async def async_get_home_devices(self, home_id: str) -> list[dict[str, Any]]:
        data = await self._request("get", f"/v1/homes/{home_id}/devices")
        return self._coerce_list(data, preferred_keys=("devices", "items", "data"))

    async def async_get_home_states(self, home_id: str) -> list[dict[str, Any]] | dict[str, Any]:
        return await self._request("get", f"/v1/homes/{home_id}/states")

    async def async_get_device_state(self, device_id: str) -> dict[str, Any]:
        data = await self._request("get", f"/v1/devices/{device_id}/secured/state")
        if isinstance(data, dict):
            _LOGGER.debug("Device state payload for %s: %s", device_id, data)
            return data
        raise MykoApiError(f"Unexpected device state payload for {device_id}: {type(data)!r}")

    async def async_reset_device_cache(self, device_id: str) -> Any:
        return await self._request("post", f"/v1/devices/{device_id}/state/resetCache", json={})

    async def async_update_device_state(self, device_id: str, parameters: dict[str, Any]) -> Any:
        """Patch device state using the same cloud endpoint as the mobile app."""
        _LOGGER.debug("Myko state update for %s: %s", device_id, parameters)
        return await self._request(
            "patch",
            f"/v1/devices/{device_id}/state",
            json={"parameters": parameters},
        )

    async def async_turn_on(
        self,
        device_id: str,
        *,
        brightness: int | None = None,
        color_temp_kelvin: int | None = None,
        mood: str | None = None,
    ) -> Any:
        parameters: dict[str, Any] = {"power": True}
        if brightness is not None:
            parameters["brightness"] = brightness
        if color_temp_kelvin is not None:
            parameters["colorTemperature"] = color_temp_kelvin
            parameters["colorMode"] = 3
        if mood is not None:
            parameters["mood"] = mood

        return await self.async_update_device_state(device_id, parameters)

    async def async_turn_off(self, device_id: str) -> Any:
        return await self.async_update_device_state(device_id, {"power": False})

    def _apply_tokens(self, tokens: MykoTokens) -> None:
        self._access_token = tokens.access_token
        self._refresh_token = tokens.refresh_token
        self._user_id = tokens.user_id
        if self._token_update_callback:
            self._token_update_callback(tokens)

    def _extract_tokens(self, data: Any) -> MykoTokens:
        if not isinstance(data, dict):
            raise MykoAuthError(f"Unexpected login payload: {type(data)!r}")

        candidate_objects = [data]
        for key in ("data", "result", "payload", "body", "auth", "tokens", "tokenSet"):
            value = data.get(key)
            if isinstance(value, dict):
                candidate_objects.append(value)

        for candidate in candidate_objects:
            access_token = (
                candidate.get("access_token")
                or candidate.get("accessToken")
                or candidate.get("id_token")
                or candidate.get("idToken")
                or candidate.get("token")
            )
            refresh_token = candidate.get("refresh_token") or candidate.get("refreshToken")

            user_id = candidate.get("userId") or candidate.get("user_id")
            user = candidate.get("user")
            if not user_id and isinstance(user, dict):
                user_id = user.get("id") or user.get("userId")
            if not user_id and access_token:
                user_id = self._extract_user_id_from_jwt(access_token)

            if access_token:
                return MykoTokens(
                    access_token=access_token,
                    refresh_token=refresh_token,
                    user_id=user_id,
                )

        raise MykoAuthError(f"Login succeeded but no access token was found: {data}")

    def _extract_user_id_from_jwt(self, token: str) -> str | None:
        """Best-effort extraction for OIDC/JWT-style access tokens."""
        parts = token.split(".")
        if len(parts) < 2:
            return None

        payload = parts[1]
        payload += "=" * (-len(payload) % 4)

        try:
            decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
            claims = json.loads(decoded.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None

        for key in ("sub", "user_id", "userId", "uid"):
            value = claims.get(key)
            if value is not None:
                return str(value)
        return None

    def _coerce_list(self, data: Any, preferred_keys: tuple[str, ...]) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in preferred_keys:
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
                if isinstance(value, dict):
                    for nested_key in preferred_keys:
                        nested_value = value.get(nested_key)
                        if isinstance(nested_value, list):
                            return [item for item in nested_value if isinstance(item, dict)]
        raise MykoApiError(f"Unexpected list payload: {data}")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        auth: bool = True,
        allow_refresh: bool = True,
    ) -> Any:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "HomeAssistant-MykoPlus/0.1",
        }
        if auth and self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        url = f"{self._base_url}{path}"
        _LOGGER.debug("Myko request %s %s", method.upper(), url)
        async with self._session.request(
            method.upper(),
            url,
            json=json,
            params=params,
            headers=headers,
        ) as response:
            try:
                response.raise_for_status()
            except ClientResponseError as err:
                text = await response.text()
                if auth and allow_refresh and err.status == 401:
                    _LOGGER.debug("Myko token expired, refreshing and retrying %s", path)
                    await self.async_reauthenticate()
                    return await self._request(
                        method,
                        path,
                        json=json,
                        params=params,
                        auth=auth,
                        allow_refresh=False,
                    )
                raise MykoApiError(f"{err.status} calling {path}: {text}") from err

            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return await response.json()
            return await response.text()

    def _ensure_authenticated(self) -> None:
        if not self._access_token:
            raise MykoAuthError("Not authenticated")
