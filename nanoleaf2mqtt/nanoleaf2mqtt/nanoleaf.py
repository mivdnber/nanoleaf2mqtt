"""Nanoleaf device control using the Open API."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import json
from collections.abc import AsyncGenerator, AsyncIterable, Iterable
import logging
from typing import Any, Literal, NamedTuple, TypedDict

import httpx
import stamina
from httpx_sse import aconnect_sse

from nanoleaf2mqtt.mqtt import Color, LightState

logger = logging.getLogger(__name__)


class NanoleafError(Exception):
    """Base exception for Nanoleaf device errors."""


@dataclass(frozen=True)
class DeviceState:
    """Represents the state of a Nanoleaf device."""

    on: bool
    brightness: int
    hue: int
    saturation: int
    color_temp: int
    color_mode: Literal["effect", "ct", "hs"]
    effect: str | None

    @classmethod
    def from_api(cls, data: dict[str, Any], effect: str | None) -> "DeviceState":
        """Create a DeviceState object from API response data."""
        return cls(
            on=data["on"]["value"],
            brightness=data["brightness"]["value"],
            hue=data["hue"]["value"],
            saturation=data["sat"]["value"],
            color_temp=data["ct"]["value"],
            color_mode=data["colorMode"],
            effect=effect,
        )

    def to_light_state(self) -> LightState:
        """Convert DeviceState to a LightState dictionary."""
        light_state = LightState(
            state="ON" if self.on else "OFF",
            brightness=int(self.brightness * 2.55),  # Scale 0-100 to 0-255
            color_mode=self.color_mode,
        )
        if self.color_mode == "ct":
            light_state["color_temp"] = self.color_temp
            light_state["color_mode"] = "color_temp"
        elif self.color_mode == "hs":
            light_state["color"] = Color(h=self.hue, s=self.saturation)
            light_state["color_mode"] = "hs"
        elif self.color_mode == "effect":
            light_state["effect"] = self.effect
        return light_state


class DeviceInfo(TypedDict, total=False):
    """Device information structure."""

    name: str
    serialNo: str
    manufacturer: str
    firmwareVersion: str
    model: str
    state: dict[str, Any]
    effects: dict[str, Any]


class DeviceSession:
    """Session for interacting with a Nanoleaf device."""

    def __init__(
        self, eui64: str, host: str, port: int = 16021, auth_token: str | None = None
    ):
        """Initialize the device session.

        Args:
            euid: Unique identifier for the device (EUI-64 format)
            host: Device hostname or IP address
            port: API port (default: 16021)
            auth_token: Authentication token (required for most operations)
        """
        self.eui64 = eui64
        self.base_url = f"http://{host}:{port}/api/v1"
        self.auth_token = auth_token
        self._state_queue: asyncio.Queue[DeviceState] = asyncio.Queue()
        # self._client = httpx.AsyncClient()

    @property
    def _client(self):
        return httpx.AsyncClient(
            timeout=httpx.Timeout(3.0),
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "DeviceSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    def _get_auth_url(self, endpoint: str = "") -> str:
        """Get URL with authentication token if available."""
        if not self.auth_token:
            raise NanoleafError("Authentication token is required")
        url = f"{self.base_url}/{self.auth_token}{endpoint}"
        return url

    async def get_info(self) -> DeviceInfo:
        """Get device information."""
        url = self._get_auth_url()
        try:
            response = await self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NanoleafError(
                f"Failed to get device info from {url}. Status: {response.status_code}"
            ) from e
        return response.json()

    async def get_state(self) -> DeviceState:
        """Get current device state.

        Returns:
            Dictionary containing the current state (on/off, brightness, color, etc.)
        """
        url = self._get_auth_url("/state")

        try:
            response = await self._client.get(url)
            response.raise_for_status()
            raw_json = response.json()
            effect = await self.get_selected_effect()
            return DeviceState.from_api(raw_json, effect)
        except httpx.HTTPError as e:
            raise NanoleafError(f"Failed to get state") from e

    async def _consolidate_current_state(self) -> None:
        """Consolidate the current state from the state queue."""
        await self._state_queue.put(await self.get_state())

    async def set_state_from_light_state(self, light_state: LightState):
        """Set the device state from a LightState object."""
        data = {}
        if (raw_state := light_state.get("state")) is not None:
            data["on"] = {"value": raw_state == "ON"}
        if (brightness := light_state.get("brightness")) is not None:
            data["brightness"] = {
                "value": int(brightness / 2.55)
            }  # Scale 0-255 to 0-100
        if (color_temp := light_state.get("color_temp")) is not None:
            data["ct"] = {"value": color_temp}
        if (
            (color := light_state.get("color")) is not None
            and "h" in color
            and "s" in color
        ):
            data["hue"] = {"value": int(color["h"])}
            data["sat"] = {"value": int(color["s"])}
        # if (effect := light_state.get("effect")) is not None:
        #     data["select"] = effect
        print(f"Setting state from LightState: {data}")
        url = self._get_auth_url("/state")
        try:
            if data:
                response = await self._client.put(url, json=data)
                response.raise_for_status()
            if (effect := light_state.get("effect")) is not None:
                response = await self._client.put(
                    self._get_auth_url("/effects"), json={"select": effect}
                )
                response.raise_for_status()
            await self._consolidate_current_state()
        except httpx.HTTPError as e:
            raise NanoleafError(
                f"Failed to set state from LightState: {light_state}"
            ) from e

    async def set_power(self, on: bool) -> None:
        """Turn the device on or off.

        Args:
            on: True to turn on, False to turn off
        """
        url = self._get_auth_url("/state")
        data = {"on": {"value": on}}
        try:
            response = await self._client.put(url, json=data)
            response.raise_for_status()
            await self._consolidate_current_state()
        except httpx.HTTPError as e:
            raise NanoleafError(
                f"Failed to set power state to {'on' if on else 'off'}"
            ) from e

    async def set_brightness(self, value: int, duration: int = 0) -> None:
        """Set brightness level.

        Args:
            value: Brightness value (0-100)
            duration: Transition duration in seconds (default: 0)
        """
        url = self._get_auth_url("/state")
        data = {"brightness": {"value": value, "duration": duration}}
        response = await self._client.put(url, json=data)
        response.raise_for_status()

    async def set_color_hsv(
        self, hue: int, saturation: int, brightness: int | None = None
    ) -> None:
        """Set color using HSV values.

        Args:
            hue: Hue value (0-360)
            saturation: Saturation (0-100)
            brightness: Optional brightness (0-100), None to keep current
        """
        url = self._get_auth_url("/state")
        data = {
            "hue": {"value": hue},
            "sat": {"value": saturation},
        }
        if brightness is not None:
            data["brightness"] = {"value": brightness}

        response = await self._client.put(url, json=data)
        response.raise_for_status()

    async def set_color_rgb(self, red: int, green: int, blue: int) -> None:
        """Set color using RGB values.

        Args:
            red: Red component (0-255)
            green: Green component (0-255)
            blue: Blue component (0-255)
        """
        # Convert RGB to HSV which is what the API expects
        # This is a simplified conversion
        r, g, b = red / 255, green / 255, blue / 255
        cmax = max(r, g, b)
        cmin = min(r, g, b)
        delta = cmax - cmin

        if delta == 0:
            hue = 0
        elif cmax == r:
            hue = 60 * (((g - b) / delta) % 6)
        elif cmax == g:
            hue = 60 * (((b - r) / delta) + 2)
        else:
            hue = 60 * (((r - g) / delta) + 4)

        saturation = 0 if cmax == 0 else (delta / cmax) * 100
        value = cmax * 100

        await self.set_color_hsv(int(hue), int(saturation), int(value))

    async def set_color_temperature(self, temperature: int) -> None:
        """Set color temperature.

        Args:
            temperature: Color temperature in Kelvin (1200-6500)
        """
        url = self._get_auth_url("/state")
        data = {"ct": {"value": temperature}}
        response = await self._client.put(url, json=data)
        response.raise_for_status()

    # async def get_effects(self) -> list[str]:
    #     """Get list of available effects."""
    #     url = self._get_auth_url("/effects/select")
    #     response = await self._client.get(url)
    #     response.raise_for_status()
    #     print(response.content, response.status_code)
    #     return response.json()
    async def get_effects(self) -> list[str]:
        """Get list of available effects."""
        url = self._get_auth_url("/effects")
        try:
            response = await self._client.put(
                url, json={"write": {"command": "requestAll"}}
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NanoleafError(
                f"Failed to get effects from {url}. Status: {response.status_code}"
            ) from e

        return response.json()

    async def get_selected_effect(self) -> str:
        """Get the name of the currently selected effect."""
        url = self._get_auth_url("/effects/select")
        try:
            response = await self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NanoleafError(f"Failed to get selected effect from {url}") from e
        return response.text.strip()

    async def stream_events(self) -> AsyncGenerator[DeviceStateChanged, None]:
        """Periodically polls the device for state changes."""
        last_state: DeviceState | None = None

        async def poll_state() -> AsyncIterable[DeviceState]:
            """Poll the device state periodically."""
            while True:
                try:
                    await self._state_queue.put(await self.get_state())
                except NanoleafError as e:
                    logger.exception(f"Error polling device {self.eui64}")
                await asyncio.sleep(5)

        async with asyncio.TaskGroup() as tg:
            tg.create_task(poll_state())
            while True:
                try:
                    current_state = await self._state_queue.get()
                    if last_state is None or current_state != last_state:
                        last_state = current_state
                        yield DeviceStateChanged(session=self, state=current_state)
                except NanoleafError as e:
                    logger.exception(f"Error polling device {self.eui64}")

    async def get(self, endpoint):
        url = self._get_auth_url(endpoint)
        try:
            response = await self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NanoleafError(f"Failed to get data from {url}") from e
        return response.content, response.status_code

    async def get_effect_names(self) -> list[str]:
        """Get the names of all available effects."""
        url = self._get_auth_url("/effects/effectsList")
        try:
            response = await self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NanoleafError(f"Failed to get effect names from {url}") from e
        return response.json()

    async def set_effect(self, effect_name: str) -> None:
        """Set the current effect.

        Args:
            effect_name: Name of the effect to activate
        """
        url = self._get_auth_url("/effects")
        data = {"select": effect_name}
        try:
            response = await self._client.put(url, json=data)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NanoleafError(f"Failed to set effect '{effect_name}'") from e
            return

    @classmethod
    async def create_auth_token(cls, host: str, port: int = 16021) -> str | None:
        """Create a new auth token by pressing the power button.

        Args:
            host: Device hostname or IP address
            port: API port (default: 16021)

        Returns:
            The new auth token

        Raises:
            NanoleafError: If token creation fails
        """
        url = f"http://{host}:{port}/api/v1/new"
        async with httpx.AsyncClient() as client:
            response = await client.post(url)

        if response.status_code == 403:
            return None

        if response.status_code != 200:
            raise NanoleafError(
                f"Failed to create auth token. Status: {response.status_code}"
            )

        try:
            return response.json()["auth_token"]
        except (json.JSONDecodeError, KeyError) as e:
            raise NanoleafError("Invalid response when creating auth token") from e


@dataclass(frozen=True)
class DeviceStateChanged:
    """Event indicating the device state has changed."""

    session: DeviceSession
    state: DeviceState


type DeviceEvent = DeviceStateChanged


class DeviceSessions:
    """Manages multiple Nanoleaf device sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, DeviceSession] = {}
        self._device_event_stream_tasks: dict[str, asyncio.Task] = {}
        self._last_state: dict[str, DeviceState] = {}
        self._lock = asyncio.Lock()
        self._global_event_queue = asyncio.Queue[DeviceEvent]()

    async def add_session(self, session: DeviceSession) -> None:
        """Add an existing device session."""
        device_id = f"{session.base_url}"

        async with self._lock:
            self._sessions[session.eui64] = session

            async def _pump_events() -> None:
                async for event in session.stream_events():
                    await self._global_event_queue.put(event)

            self._device_event_stream_tasks[device_id] = asyncio.create_task(
                _pump_events()
            )

    async def remove_session(self, session: DeviceSession) -> None:
        """Remove a device session."""
        async with self._lock:
            self._sessions.pop(session.eui64, None)
            self._last_state.pop(session.eui64, None)
            self._device_event_stream_tasks.pop(session.eui64).cancel()

    async def has_session(self, eui64: str) -> bool:
        """Check if a session for the given EUI-64 exists."""
        async with self._lock:
            return eui64 in self._sessions

    async def get_session(self, eui64: str) -> DeviceSession | None:
        """Get a device session by EUI-64."""
        async with self._lock:
            return self._sessions.get(eui64)

    async def stream_events(self) -> AsyncGenerator[DeviceEvent, None]:
        """Stream device events."""
        while True:
            yield await self._global_event_queue.get()
