"""Configuration settings for the Nanoleaf to MQTT bridge."""

import os
from typing import Final

from dotenv import load_dotenv

load_dotenv()

# MQTT Configuration
MQTT_HOST: Final[str] = os.getenv("MQTT_HOST", "localhost")
"""MQTT broker hostname or IP address."""

MQTT_PORT: Final[int] = int(os.getenv("MQTT_PORT", "1883"))
"""MQTT broker port number."""

MQTT_USER: Final[str | None] = os.getenv("MQTT_USER")
"""MQTT username. Set via MQTT_USER environment variable."""

MQTT_PASSWORD: Final[str | None] = os.getenv("MQTT_PASSWORD")
"""MQTT password. Set via MQTT_PASSWORD environment variable."""

LOG_LEVEL: Final[str] = os.getenv("LOG_LEVEL", "INFO").upper()
"""Logging level for the application. Default is INFO."""

DATABASE_PATH: Final[str] = os.getenv("DATABASE_PATH", "nanoleaf2mqtt.db")
"""Path to the SQLite database file. Default is 'nanoleaf2mqtt.db' in the working directory."""
