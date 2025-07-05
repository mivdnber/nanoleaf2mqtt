# Nanoleaf2MQTT

Control your Nanoleaf devices with MQTT using the Nanoleaf Open API

## Warning

This is a mostly vibe coded piece of software. Very much in an alpha state. It works on my machine. I take no responsibility for bricked devices, although I will join you in your sadness should they break. I'll even allow you to be slightly angry with me for a little while, if that helps you cope.

## But why

I wanted to control my Nanoleaf Outdoor String Lights in Home Assistant. They are Matter-compatible, but Matter doesn't support scenes / effects (yet), which is a shame.
The Nanoleaf integration exists, but it currently does not work with the string lights.

## Compatibility

Currently only my Nanoleaf Outdoor String Lights are tested. Other devices may work, or combust spontaneously.

## Setup for Home Assistant

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmivdnber%2Fnanoleaf2mqtt)

1. Setup the MQTT integration with the Mosquitto MQTT broker
1. Add the add-on repository URL to your Home Assistant instance (click the My Home Assistant badge above)
1. Install the Nanoleaf2MQTT add-on
1. In the Nanoleaf app, press "Connect to API" in Device Settings
1. nanoleaf2mqtt should magically set up a connection to your device
1. Your device should be discovered and available under the MQTT integration
