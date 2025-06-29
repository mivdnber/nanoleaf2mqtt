import asyncio
import logging
import logging.config
import sys
from collections.abc import AsyncIterator

from aiostream.stream import merge

from nanoleaf2mqtt.config import (
    LOG_LEVEL,
    MQTT_HOST,
    MQTT_PASSWORD,
    MQTT_PORT,
    MQTT_USER,
)
from nanoleaf2mqtt.database import Database, StoredDevice
from nanoleaf2mqtt.discovery import (
    DeviceFound,
    DevicePresent,
    DeviceRemoved,
    DiscoveredDevice,
    DiscoveryEvent,
    NanoleafDiscovery,
)
from nanoleaf2mqtt.mqtt import LightState, MqttClient, MqttCommand, MqttEvent
from nanoleaf2mqtt.nanoleaf import (
    DeviceEvent,
    DeviceSession,
    DeviceSessions,
    DeviceStateChanged,
    NanoleafError,
)

LOGGING_CONFIG = {
    "version": 1,
    "handlers": {
        "default": {
            "class": "logging.StreamHandler",
            "formatter": "nanoleaf2mqtt",
            "stream": "ext://sys.stderr",
            "level": LOG_LEVEL,
        }
    },
    "formatters": {
        "nanoleaf2mqtt": {
            "format": "[%(asctime)s] %(levelname)s %(name)s - %(message)s",
            # "datefmt": "%Y-%m-%d %H:%M:%S",
        }
    },
    "loggers": {
        "httpx": {
            "handlers": ["default"],
            "level": "CRITICAL",
        },
        "httpcore": {
            "handlers": ["default"],
            "level": "CRITICAL",
        },
    },
    "root": {
        "handlers": ["default"],
        "level": LOG_LEVEL,
    },
}

logging.config.dictConfig(LOGGING_CONFIG)

logger = logging.getLogger(__name__)


async def discovery_events(
    discovery: NanoleafDiscovery,
) -> AsyncIterator[DiscoveryEvent]:
    async def _streamed_events() -> AsyncIterator[DiscoveryEvent]:
        async for event in discovery.stream_events():
            yield event

    async def _periodic_events() -> AsyncIterator[DiscoveryEvent]:
        while True:
            for device in discovery.get_devices():
                yield DevicePresent(device)
            await asyncio.sleep(10)

    async with merge(_streamed_events(), _periodic_events()).stream() as stream:
        async for event in stream:
            yield event


async def mqtt_events(client: MqttClient) -> AsyncIterator[MqttEvent]:
    async for event in client.stream_events():
        yield event


async def device_events(device_sessions: DeviceSessions) -> AsyncIterator[DeviceEvent]:
    """Stream device events from active sessions."""
    while True:
        async for event in device_sessions.stream_events():
            yield event


async def handle_device_present(
    device: DiscoveredDevice,
    db: Database,
    sessions: DeviceSessions,
    mqtt_client: MqttClient,
) -> tuple[StoredDevice, DeviceSession] | None:
    """Handle a DevicePresent event by ensuring the device has a valid token."""
    # Check if we already have a token for this device
    stored_device = db.get_device(device.eui64)
    if not stored_device or not stored_device.token:
        logger.debug("No stored device or token for %s", device.name)
        try:
            # Try to get a new auth token
            token = await DeviceSession.create_auth_token(
                host=device.hostname, port=device.port
            )
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected error getting token for %s", device.name)
            return
        if token is None:
            logger.error("Not allowed to create token for %s", device.name)
            return
        logger.info("Successfully got token for %s", device.name)
        # Create a new device record with the token
        stored_device = StoredDevice(
            eui64=device.eui64,
            name=device.name,
            nanoleaf_id=device.properties.get(b"id", b"").decode(),
            model_id=device.properties.get(b"md", b"").decode(),
            firmware_version=device.properties.get(b"srcvers", b"").decode(),
            token=token,
        )
        db.store_device(stored_device)

    session = await sessions.get_session(device.eui64)
    if session is not None:
        logger.debug("Session already exists for %s", device.name)
    else:
        session = DeviceSession(
            device.eui64, device.hostname, device.port, auth_token=stored_device.token
        )
        await sessions.add_session(session)
        return stored_device, session


async def main() -> None:
    logger.info("Starting main")
    # Initialize the database
    db = Database()
    sessions = DeviceSessions()

    with NanoleafDiscovery() as discovery:
        logger.debug("Discovery started")
        async with MqttClient(
            broker=MQTT_HOST,
            port=MQTT_PORT,
            username=MQTT_USER,
            password=MQTT_PASSWORD,
        ) as client:
            logger.debug("MQTT client started")
            async with merge(
                discovery_events(discovery),
                mqtt_events(client),
                device_events(sessions),
            ).stream() as stream:
                logger.debug("Stream started")
                async for event in stream:
                    match event:
                        case DeviceFound(device):
                            logger.info(f"Device found: {device.name} ({device.eui64})")
                            match await handle_device_present(
                                device, db, sessions, client
                            ):
                                case (stored_device, session):
                                    effect_names = await session.get_effect_names()
                                    await client.publish_discovery(
                                        device_id=device.eui64,
                                        device_name=device.name,
                                        model=stored_device.model_id,
                                        manufacturer="nanoleaf",
                                        sw_version=stored_device.firmware_version,
                                        effect_names=effect_names,
                                    )
                                    state = await session.get_state()
                                    await client.publish_state(
                                        device.eui64, state.to_light_state()
                                    )

                        case DeviceRemoved(device):
                            logger.info(f"Device removed: {device.name}")
                            stored_device = db.get_device(device.eui64)
                            if stored_device and stored_device.token:
                                session = DeviceSession(
                                    device.eui64,
                                    device.hostname,
                                    device.port,
                                    auth_token=stored_device.token,
                                )
                                await sessions.remove_session(session)
                        case DevicePresent(device):
                            logger.debug(f"Device present: {device.name}")
                            match await handle_device_present(
                                device, db, sessions, client
                            ):
                                case stored_device, session:
                                    effect_names = await session.get_effect_names()
                                    await client.publish_discovery(
                                        device_id=device.eui64,
                                        device_name=device.name,
                                        model=stored_device.model_id,
                                        manufacturer="nanoleaf",
                                        sw_version=stored_device.firmware_version,
                                        effect_names=effect_names,
                                    )
                                    state = await session.get_state()
                                    await client.publish_state(
                                        device.eui64, state.to_light_state()
                                    )
                        case DeviceStateChanged(session, state):
                            logger.info(
                                f"Device state changed: {session.eui64} {state}"
                            )
                            await client.publish_state(
                                session.eui64, state.to_light_state()
                            )
                        case MqttCommand(device_id, state):
                            logger.info(
                                f"MQTT command received for {device_id}: {state}"
                            )
                            session = await sessions.get_session(device_id)
                            if session is None:
                                logger.warning(f"No session found for {device_id}")
                                continue
                            try:
                                await session.set_state_from_light_state(state)
                            except NanoleafError as e:
                                logger.exception(
                                    f"Failed to set state for {device_id}: {e}"
                                )


if __name__ == "__main__":
    asyncio.run(main())
