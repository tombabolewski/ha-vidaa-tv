# Vidaa TV - Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Home Assistant custom component for controlling Hisense/Vidaa Smart TVs. Communicates directly with the TV's built-in SSL broker — no cloud, no MQTT bridge needed.

## Features

- **Power on/off** with Wake-on-LAN support
- **Volume control** — up/down/set/mute
- **Input source selection** and **app launching** (Netflix, YouTube, Prime Video, Disney+, etc.)
- **34 remote buttons** as HA button entities (d-pad, playback, channel, numbers, colors)
- **Sensors** — current app and current source
- **Mute switch** — toggle with state awareness
- **SSDP auto-discovery** — TV detected automatically
- **PIN pairing** — secure authentication via TV screen

## Entities

| Platform | Entities | Description |
|----------|----------|-------------|
| Media Player | 1 | Volume, power, source, app launching |
| Remote | 1 | Key sending, activity (app) support |
| Button | 33 | Individual remote keys (18 enabled + 15 disabled by default) |
| Sensor | 2 | Current App, Current Source |
| Switch | 1 | Mute toggle |

Disabled-by-default buttons (enable from device page): color buttons (red/green/yellow/blue), number keys (0-9), subtitle.

## Installation

### HACS (Recommended)

1. Add this repository as a custom repository in HACS
2. Install "Vidaa TV"
3. Restart Home Assistant

### Manual

1. Copy `custom_components/vidaa_tv/` to your HA `config/custom_components/` directory
2. Restart Home Assistant

## Setup

1. Go to **Settings** > **Integrations** > **Add Integration** > **Vidaa TV**
2. Enter your TV's IP address (or wait for SSDP auto-discovery)
3. A PIN will appear on your TV — enter it in the HA UI
4. Done. All entities appear under the device.

No certificates or manual config needed — the library handles authentication automatically.

## Services

| Service | Description |
|---------|-------------|
| `vidaa_tv.send_key` | Send any remote key (e.g. `KEY_HOME`, `KEY_MUTE`) |
| `vidaa_tv.launch_app` | Launch an app by name (e.g. `netflix`, `youtube`) |

## Dashboard Remote Card

A ready-made Lovelace remote card is included in [`dashboard-remote-card.yaml`](dashboard-remote-card.yaml). Uses standard HA cards only (no HACS frontend dependencies):

- Power / Info / Home row
- D-pad (up/down/left/right/OK)
- Back / Menu / Exit
- Channel up/down + mute
- Media player card with volume slider
- Playback controls (rewind/play/pause/stop/ff)
- Current app and source sensors

Copy the YAML into a manual card. Adjust entity IDs to match your TV's name.

## Requirements

- Hisense TV with Vidaa OS
- TV and Home Assistant on the same network
- Home Assistant 2024.1+

## Library

This integration uses [vidaa-control](https://pypi.org/project/vidaa-control/) ([source](https://github.com/tombabolewski/vidaa-control)) — a standalone Python library for Vidaa TV communication.

## License

MIT
