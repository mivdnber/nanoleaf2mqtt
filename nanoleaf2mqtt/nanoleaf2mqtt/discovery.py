"""Nanoleaf device discovery using mDNS/zeroconf."""

import asyncio
import logging
from collections.abc import AsyncGenerator, Iterable
from dataclasses import dataclass
from typing import Any

from zeroconf import ServiceBrowser, ServiceInfo, ServiceStateChange, Zeroconf

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredDevice:
    """Represents a discovered Nanoleaf device."""

    name: str
    hostname: str
    port: int
    eui64: str
    properties: dict[bytes, Any]

    @classmethod
    def from_service_info(cls, info: ServiceInfo) -> "DiscoveredDevice":
        """Create a DiscoveredDevice from zeroconf ServiceInfo."""
        name = info.name.split(".")[0]  # Remove .local suffix
        eui64 = info.properties.get(b"eui64", b"").decode()
        hostname = info.server or name
        return cls(
            name=name,
            hostname=hostname,
            port=info.port,
            eui64=eui64,
            properties=info.properties or {},
        )


@dataclass
class DeviceFound:
    device: DiscoveredDevice


@dataclass
class DeviceRemoved:
    device: DiscoveredDevice


@dataclass
class DevicePresent:
    device: DiscoveredDevice


type DiscoveryEvent = DeviceFound | DeviceRemoved | DevicePresent


class NanoleafDiscovery:
    """Handles discovery of Nanoleaf devices on the local network using mDNS."""

    def __init__(self):
        self.zeroconf = Zeroconf()
        # Index devices by name for easy lookup
        self._devices: dict[str, DiscoveredDevice] = {}
        self.browser: ServiceBrowser | None = None
        self._started = False
        self._event_queue: asyncio.Queue[DiscoveryEvent] = asyncio.Queue()

    def on_service_state_change(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        """Handle changes in the discovered services."""
        match state_change:
            case ServiceStateChange.Added:
                info = zeroconf.get_service_info(service_type, name)
                if info and info.addresses:
                    device = DiscoveredDevice.from_service_info(info)
                    self._devices[device.name] = device
                    logger.info(f"Added Nanoleaf device: {device}")
                    self._event_queue.put_nowait(DeviceFound(device))
            case ServiceStateChange.Removed:
                # Find device by name
                if name in self._devices:
                    device = self._devices.pop(name)
                    logger.info(f"Removed Nanoleaf device: {device}")
                    self._event_queue.put_nowait(DeviceRemoved(device))

    def start(self) -> None:
        """Start the discovery service."""
        if not self._started:
            self.browser = ServiceBrowser(
                self.zeroconf,
                "_nanoleafapi._tcp.local.",
                handlers=[self.on_service_state_change],
            )
            # Mark as started last to ensure idempotency
            self._started = True

    def stop(self) -> None:
        """Stop the discovery service and clean up resources."""
        if self._started:
            if self.browser:
                self.browser.cancel()
                self.browser = None
            self.zeroconf.close()
            self._started = False

    def __enter__(self) -> "NanoleafDiscovery":
        """Context manager entry point."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensures resources are cleaned up."""
        self.stop()

    def get_devices(self) -> Iterable[DiscoveredDevice]:
        """Return a dictionary of discovered Nanoleaf devices.

        Returns:
            A dictionary mapping device names to DiscoveredDevice objects.
        """
        return self._devices.values()

    async def stream_events(self) -> AsyncGenerator[DiscoveryEvent]:
        while True:
            yield await self._event_queue.get()

    # For backwards compatibility with existing code
    def __del__(self) -> None:
        """Ensure resources are cleaned up when the object is garbage collected."""
        self.stop()
