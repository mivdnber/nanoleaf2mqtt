# nanoleaf2mqtt

Control your Nanoleaf devices with MQTT using the Nanoleaf Open API

## Warning

This is a mostly vibe coded piece of software. Very much in an alpha state. It works on my machine. I take no responsibility for bricked devices, although I will join you in your sadness should they break. I'll even allow you to be slightly angry with me for a little while, if that helps you cope.

## But why

I wanted to control my Nanoleaf Outdoor String Lights in Home Assistant. They are Matter-compatible, but Matter doesn't support scenes / effects (yet), which is a shame.
The Nanoleaf integration exists, but it currently does not work with the string lights.

## Compatibility

Currently only my Nanoleaf Outdoor String Lights are tested. Other devices may work, or combust spontaneously.

## Setup for Home Assistant

1. Setup the MQTT integration with the Mosquitto MQTT broker
1. Install the nanoleaf2mqtt addon
1. In the Nanoleaf app, enable API access for your device
1. nanoleaf2mqtt should magically set up a connection to your device
1. If you're using Home Assistant, your device should be discovered and available under the MQTT integration
