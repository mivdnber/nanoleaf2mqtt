"""
Token management for Nanoleaf devices using SQLite.

This module provides functionality to store, retrieve, and manage Nanoleaf device tokens
using an SQLite database with eui64 as the primary key.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class StoredDevice:
    eui64: str  # mdns: eui64
    name: str  # User-friendly device name
    nanoleaf_id: str  # mdns: id
    model_id: str  # mdns: md
    firmware_version: str  # mdns: srcvers
    token: str


class Database:
    """Manages Nanoleaf device information in an SQLite database.

    The database uses eui64 as the primary key to store and retrieve device information.
    """

    def __init__(self, db_path: str = "nanoleaf2mqtt.db"):
        """Initialize the Database with the path to the SQLite database.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create and return a new database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn

    def _init_db(self) -> None:
        """Initialize the database schema if it doesn't exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    eui64 TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    nanoleaf_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    firmware_version TEXT NOT NULL,
                    token TEXT NOT NULL
                )
            """
            )
            conn.commit()

    def store_device(self, device: StoredDevice) -> None:
        """Store or update a device in the database.

        Args:
            device: The StoredDevice object containing device information.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO devices (eui64, name, nanoleaf_id, model_id, firmware_version, token)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(eui64) DO UPDATE SET
                    name = excluded.name,
                    nanoleaf_id = excluded.nanoleaf_id,
                    model_id = excluded.model_id,
                    firmware_version = excluded.firmware_version,
                    token = excluded.token
                """,
                (
                    device.eui64,
                    device.name,
                    device.nanoleaf_id,
                    device.model_id,
                    device.firmware_version,
                    device.token,
                ),
            )
            conn.commit()

    def get_device(self, eui64: str) -> StoredDevice | None:
        """Retrieve a device by its EUI64.

        Args:
            eui64: The device's EUI64 identifier.

        Returns:
            The StoredDevice if found, None otherwise.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT eui64, name, nanoleaf_id, model_id, firmware_version, token
                FROM devices
                WHERE eui64 = ?
                """,
                (eui64,),
            )
            row = cursor.fetchone()
            if row:
                return StoredDevice(
                    eui64=row["eui64"],
                    name=row["name"],
                    nanoleaf_id=row["nanoleaf_id"],
                    model_id=row["model_id"],
                    firmware_version=row["firmware_version"],
                    token=row["token"],
                )
            return None

    def delete_device(self, eui64: str) -> bool:
        """Delete a device from the database.

        Args:
            eui64: The device's EUI64 identifier.

        Returns:
            True if a device was deleted, False otherwise.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM devices WHERE eui64 = ?", (eui64,))
            conn.commit()
            return cursor.rowcount > 0

    def list_devices(self) -> list[StoredDevice]:
        """List all devices in the database.

        Returns:
            A list of StoredDevice objects for all devices in the database.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT eui64, name, nanoleaf_id, model_id, firmware_version, token
                FROM devices
                """
            )
            return [
                StoredDevice(
                    eui64=row["eui64"],
                    name=row["name"],
                    nanoleaf_id=row["nanoleaf_id"],
                    model_id=row["model_id"],
                    firmware_version=row["firmware_version"],
                    token=row["token"],
                )
                for row in cursor.fetchall()
            ]
