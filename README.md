# Vidaa TV - Home Assistant Custom Component

Home Assistant integration for controlling Hisense/Vidaa TVs via their built-in MQTT broker.

## Features

- Power on/off (with Wake-on-LAN support)
- Volume control (up/down/set/mute)
- Input source selection
- App launching (Netflix, YouTube, Prime Video, Disney+, etc.)
- Remote key sending
- SSDP auto-discovery

## Requirements

- Hisense TV with Vidaa OS
- SSL client certificates (`vidaa_client.pem` and `vidaa_client.key`)
- TV and Home Assistant on the same network

## Installation

### HACS (Recommended)

1. Add this repository as a custom repository in HACS
2. Install "Vidaa TV"
3. Restart Home Assistant

### Manual

1. Copy `custom_components/vidaa_tv/` to your HA `config/custom_components/` directory
2. Restart Home Assistant

## Setup

1. Place SSL certificates in `config/certs/`:
   - `vidaa_client.pem`
   - `vidaa_client.key`

2. Go to **Settings** > **Integrations** > **Add Integration** > **Vidaa TV**

3. Enter your TV's IP address

4. A PIN will appear on your TV - enter it in the HA UI

## Entities

- **Media Player**: Volume, power, source selection, app launching
- **Remote**: Key sending, activity (app) support

## Services

- `vidaa_tv.send_key`: Send a remote key press
- `vidaa_tv.launch_app`: Launch an app on the TV
