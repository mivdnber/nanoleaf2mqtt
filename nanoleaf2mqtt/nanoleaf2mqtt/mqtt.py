"""MQTT client for Home Assistant integration with Nanoleaf devices using aiomqtt."""

import asyncio
from dataclasses import dataclass
import json
import logging
import types
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, TypedDict

from aiomqtt import Client, MqttError, Will
from aiomqtt.types import PayloadType

logger = logging.getLogger(__name__)


class Color(TypedDict, total=True):
    """Color representation for MQTT messages."""

    h: float
    s: float


class LightState(TypedDict, total=False):
    """Light state representation for MQTT messages."""

    state: str  # "ON" or "OFF"
    brightness: int  # 0-255
    color_temp: int  # Kelvin
    color: Color
    effect: str | None  # Current effect name
    transition: int  # Transition time in seconds
    color_mode: str


@dataclass(frozen=True)
class MqttCommand:
    device_id: str
    state: LightState


type MqttEvent = MqttCommand


class MqttClient:
    """MQTT client for Home Assistant integration.

    Handles device discovery and light state updates for Nanoleaf devices.
    """

    def __init__(
        self,
        broker: str = "localhost",
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
        discovery_prefix: str = "homeassistant",
        node_id: str = "nanoleaf2mqtt",
    ) -> None:
        """Initialize MQTT client.

        Args:
            broker: MQTT broker hostname or IP
            port: MQTT broker port
            username: MQTT username (if required)
            password: MQTT password (if required)
            discovery_prefix: MQTT discovery prefix (default: homeassistant)
            node_id: Unique identifier for this bridge instance
        """
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.discovery_prefix = discovery_prefix
        self.node_id = node_id

        self._client: Client | None = None
        self._connected = asyncio.Event()
        self._disconnect_event = asyncio.Event()
        self._message_queue: asyncio.Queue[MqttEvent] = asyncio.Queue()
        self._message_callbacks: dict[str, Callable[[LightState], Awaitable[None]]] = {}
        self._subscriptions: set[str] = set()
        self._client_task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> "MqttClient":
        """Async context manager entry point.

        Returns:
            The MqttClient instance
        """
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Async context manager exit - ensures resources are cleaned up.

        Args:
            exc_type: The exception type if an exception was raised
            exc_val: The exception value if an exception was raised
            exc_tb: The traceback if an exception was raised
        """
        await self.disconnect()

    async def connect(self) -> None:
        """Connect to the MQTT broker and start the message handler."""
        if self._client_task is not None and not self._client_task.done():
            logger.warning("MQTT client is already running")
            return

        self._disconnect_event.clear()
        self._client_task = asyncio.create_task(self._run_client())

        try:
            # Wait for connection to be established
            await asyncio.wait_for(self._connected.wait(), timeout=10.0)
            logger.info(f"Connected to MQTT broker at {self.broker}:{self.port}")
        except TimeoutError:
            logger.error("Timeout waiting for MQTT connection")
            await self.disconnect()
            raise

    async def _run_client(self) -> None:
        """Run the MQTT client loop."""
        reconnect_interval = 1
        while not self._disconnect_event.is_set():
            try:
                async with Client(
                    hostname=self.broker,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    clean_session=True,
                    will=Will(
                        topic=f"{self.node_id}/status",
                        payload="offline",
                        retain=True,
                        qos=1,
                    ),
                ) as client:
                    self._client = client
                    self._connected.set()

                    # Resubscribe to all topics
                    for topic in self._subscriptions:
                        await client.subscribe(topic, qos=1)

                    # Publish online status
                    await client.publish(
                        f"{self.node_id}/status",
                        payload="online",
                        retain=True,
                        qos=1,
                    )

                    # Process incoming messages
                    async for message in client.messages:
                        await self._handle_incoming_message(
                            message.topic.value, message.payload
                        )

            except MqttError as e:
                self._connected.clear()
                logger.error(f"MQTT connection error: {e}")

                # Exponential backoff for reconnection
                await asyncio.sleep(reconnect_interval)
                reconnect_interval = min(
                    reconnect_interval * 2, 60
                )  # Cap at 60 seconds
                continue

            except asyncio.CancelledError:
                logger.debug("MQTT client task cancelled")
                break

            except Exception as e:
                logger.error(f"Unexpected error in MQTT client: {e}", exc_info=True)
                self._connected.clear()
                await asyncio.sleep(5)  # Prevent tight loop on unexpected errors
                continue

            # If we get here, the connection was lost
            self._connected.clear()
            logger.warning("MQTT connection lost, reconnecting...")
            await asyncio.sleep(1)

    async def disconnect(self) -> None:
        """Disconnect from the MQTT broker."""
        if self._client_task is None:
            return

        self._disconnect_event.set()
        self._client_task.cancel()

        try:
            await asyncio.wait_for(self._client_task, timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            logger.warning("Timeout waiting for MQTT client to disconnect")

        self._client = None
        self._client_task = None
        self._connected.clear()
        logger.info("Disconnected from MQTT broker")

    async def publish_discovery(
        self,
        device_id: str,
        device_name: str,
        model: str,
        manufacturer: str = "Nanoleaf",
        sw_version: str = "1.0",
        effect_names: list[str] | None = None,
    ) -> None:
        """Publish Home Assistant MQTT discovery message for a light device.

        Args:
            device_id: Unique identifier for the device
            device_name: Human-readable name for the device
            model: Device model name
            manufacturer: Device manufacturer (default: Nanoleaf)
            sw_version: Firmware version (default: 1.0)
            suggested_area: Suggested area for the device (e.g., "Living Room")
        """
        if not self._connected.is_set():
            raise RuntimeError("Not connected to MQTT broker")
        if self._client is None:
            raise RuntimeError("MQTT client not initialized")

        discovery_topic = (
            f"{self.discovery_prefix}/light/{self.node_id}_{device_id}/config"
        )

        device_info = {
            "identifiers": [f"{self.node_id}_{device_id}"],
            "name": device_name,
            "model": model,
            "manufacturer": manufacturer,
            "sw_version": sw_version,
        }

        discovery_payload = {
            "name": device_name,
            "unique_id": f"{self.node_id}_{device_id}",
            "device": device_info,
            "schema": "json",
            "command_topic": f"{self.node_id}/{device_id}/set",
            "state_topic": f"{self.node_id}/{device_id}/state",
            "brightness": True,
            "color_mode": True,
            "supported_color_modes": ["color_temp", "hs"],
            "color_temp_kelvin": True,
            "min_kelvin": 1200,
            "max_kelvin": 6500,
            "effect": True,
            "effect_list": effect_names or [],
            "optimistic": False,
            "qos": 1,
            "retain": True,
        }

        await self._client.publish(
            discovery_topic,
            payload=json.dumps(discovery_payload),
            retain=True,
            qos=1,
        )

        # Subscribe to command topic
        command_topic = f"{self.node_id}/{device_id}/set"
        await self._subscribe_topic(command_topic)
        logger.info(
            f"Published discovery for {device_name} and subscribed to {command_topic}"
        )

    async def _subscribe_topic(self, topic: str) -> None:
        """Subscribe to a topic if not already subscribed."""
        if topic in self._subscriptions or self._client is None:
            return

        await self._client.subscribe(topic, qos=1)
        self._subscriptions.add(topic)
        logger.debug(f"Subscribed to MQTT topic: {topic}")

    async def _handle_incoming_message(self, topic: str, payload: PayloadType) -> None:
        """Handle incoming MQTT message."""
        try:
            # Extract device_id from topic: {node_id}/{device_id}/set
            parts = topic.split("/")
            if len(parts) < 3 or parts[-1] != "set":
                return

            device_id = parts[-2]

            # Parse the message payload
            if isinstance(payload, bytes | bytearray):
                payload_str = payload.decode("utf-8")
            else:
                payload_str = str(payload)

            payload_data = json.loads(payload_str)

            # Queue the message for async processing
            await self._handle_command(device_id, payload_data)

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON payload in MQTT message on topic {topic}")
        except Exception as e:
            logger.error(
                f"Error processing MQTT message on topic {topic}: {e}", exc_info=True
            )

    async def publish_state(
        self,
        device_id: str,
        state: LightState,
    ) -> None:
        """Publish light state to MQTT.

        Args:
            device_id: Device identifier
            state: Light state to publish

        Raises:
            RuntimeError: If not connected to MQTT broker or client not initialized
        """
        if not self._connected.is_set():
            raise RuntimeError("Not connected to MQTT broker")
        if self._client is None:
            raise RuntimeError("MQTT client not initialized")

        topic = f"{self.node_id}/{device_id}/state"
        try:
            await self._client.publish(
                topic,
                payload=json.dumps(state),
                retain=True,
                qos=1,
            )
        except Exception as e:
            logger.error(f"Failed to publish state to {topic}: {e}")
            raise

    async def _handle_command(self, device_id: str, payload: dict[str, Any]) -> None:
        """Handle incoming MQTT command.

        Args:
            device_id: The ID of the device that sent the command
            payload: The command payload as a dictionary
        """
        try:
            # Convert the command to a LightState dictionary
            state: LightState = {
                "state": payload.get("state", "OFF").upper(),
            }

            if "brightness" in payload:
                state["brightness"] = int(payload["brightness"])

            if "color_temp" in payload:
                state["color_temp"] = int(payload["color_temp"])
                state["color_mode"] = "color_temp"

            if "color" in payload:
                color = payload["color"]
                state["color"] = {}
                if "h" in color and "s" in color:
                    state["color"]["h"] = float(color["h"])
                    state["color"]["s"] = float(color["s"])
                    state["color_mode"] = "hs"
                if "r" in color and "g" in color and "b" in color:
                    state["color"]["r"] = int(color["r"])
                    state["color"]["g"] = int(color["g"])
                    state["color"]["b"] = int(color["b"])
                    state["color_mode"] = "rgb"

            if "effect" in payload and payload["effect"] is not None:
                state["effect"] = str(payload["effect"])

            if "transition" in payload:
                state["transition"] = int(payload["transition"])

            # Put the state in the queue for processing
            await self._message_queue.put(MqttCommand(device_id=device_id, state=state))

            # If there's a registered callback, call it
            if device_id in self._message_callbacks:
                await self._message_callbacks[device_id](state)

        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"Invalid command format for device {device_id}: {e}")
        except Exception as e:
            logger.error(
                f"Error handling command for device {device_id}: {e}", exc_info=True
            )

    async def stream_events(self) -> AsyncGenerator[MqttEvent]:
        """Stream MQTT state changes as they arrive.

        Yields:
            A tuple of (device_id, state) for each state change

        The generator will continue to yield events until the client is disconnected.
        """
        while self._connected.is_set():
            try:
                yield await asyncio.wait_for(self._message_queue.get(), timeout=1.0)
            except TimeoutError:
                if not self._connected.is_set():
                    break
                continue

    async def register_command_callback(
        self,
        device_id: str,
        callback: Callable[[LightState], Awaitable[None]],
    ) -> None:
        """Register a callback for command messages for a specific device.

        Args:
            device_id: Device identifier to register the callback for
            callback: Async callback function that receives LightState

        Raises:
            ValueError: If the callback is not callable
        """
        if not callable(callback):
            raise ValueError("Callback must be callable")

        self._message_callbacks[device_id] = callback
        logger.debug(f"Registered command callback for device {device_id}")

    async def unregister_command_callback(self, device_id: str) -> None:
        """Unregister a command callback for a device.

        Args:
            device_id: Device identifier to unregister
        """
        if device_id in self._message_callbacks:
            del self._message_callbacks[device_id]
            logger.debug(f"Unregistered command callback for device {device_id}")
