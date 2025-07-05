#!/usr/bin/with-contenv bashio

cd /app
MQTT_HOST=$(bashio::services mqtt "host")
MQTT_USER=$(bashio::services mqtt "username")
MQTT_PASSWORD=$(bashio::services mqtt "password")
DATABASE_PATH="/data/nanoleaf2mqtt.db"
bashio::log.info "Starting Nanoleaf2MQTT with MQTT host: $MQTT_HOST, user: $MQTT_USER, database path: $DATABASE_PATH"
/app/.venv/bin/python -m nanoleaf2mqtt.main 