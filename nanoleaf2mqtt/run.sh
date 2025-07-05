#!/usr/bin/with-contenv bashio

cd /app
MQTT_HOST=$(bashio::services mqtt "host")
MQTT_USER=$(bashio::services mqtt "username")
MQTT_PASSWORD=$(bashio::services mqtt "password")
DATABASE_PATH="/data/nanoleaf2mqtt.db"
/app/.venv/bin/python -m nanoleaf2mqtt.main 