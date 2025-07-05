#!/usr/bin/with-contenv bashio

cd /app
export MQTT_HOST=$(bashio::services mqtt "host")
export MQTT_USER=$(bashio::services mqtt "username")
export MQTT_PASSWORD=$(bashio::services mqtt "password")
export MQTT_PORT=$(bashio::services mqtt "port")

DATABASE_PATH="/data/nanoleaf2mqtt.db"
bashio::log.info "Starting Nanoleaf2MQTT with MQTT host: $MQTT_HOST, port: $MQTT_PORT, user: $MQTT_USER, database path: $DATABASE_PATH"
/app/.venv/bin/python -m nanoleaf2mqtt.main