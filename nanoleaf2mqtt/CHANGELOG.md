# Changelog

## 0.1.15 - 2025-12-06

⚠️ **This release will require you to pair your devices again. This won't happen again in later releases, pinky swear this time. So sorry!** ⚠️

- Store the database file in the add-on's data directory, ensuring persistence across updates and reboots.

## 0.1.14 - 2025-12-06

- Fix compatibility with Home Assistant 2025.12 by removing `color_mode` from the MQTT device discovery payload.

## 0.1.13 - 2025-10-19

⚠️ **This release will require you to pair your devices again. This won't happen again in later releases, sorry!** ⚠️

- Fix device connections being wiped on Home Assistant updates, and sometimes reboots. The file containing the API tokens was being stored inside the container instead of the add-on's data directory.
