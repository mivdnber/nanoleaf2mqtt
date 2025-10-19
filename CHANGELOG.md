# Changelog

## 0.1.13 - 2025-10-19

⚠️ **This release will require you to pair your devices again. This won't happen again in later releases, sorry!** ⚠️

- Fix device connections being wiped on Home Assistant updates, and sometimes reboots. The file containing the API tokens was being stored inside the container instead of the add-on's data directory.
