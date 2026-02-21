"""Constants for the Vidaa TV integration."""

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "vidaa_tv"

# Configuration keys
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_MAC: Final = "mac"
CONF_NAME: Final = "name"
CONF_DEVICE_ID: Final = "device_id"
CONF_MODEL: Final = "model"
CONF_SW_VERSION: Final = "sw_version"
# Default values
DEFAULT_PORT: Final = 36669
DEFAULT_NAME: Final = "Vidaa TV"

# Timeouts
TIMEOUT_CONNECT: Final = 10
TIMEOUT_COMMAND: Final = 5
TIMEOUT_DISCOVERY: Final = 5

# Scan interval for polling
SCAN_INTERVAL: Final = 30

# Services
SERVICE_SEND_KEY: Final = "send_key"
SERVICE_LAUNCH_APP: Final = "launch_app"

# Attributes
ATTR_KEY: Final = "key"
ATTR_APP: Final = "app"

# States
STATE_FAKE_SLEEP: Final = "fake_sleep_0"

# Platform types
PLATFORMS: Final = [
    Platform.MEDIA_PLAYER,
    Platform.REMOTE,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]

# Button key definitions: (key_id, name, icon, vidaa_key, enabled_by_default)
BUTTON_KEYS: Final = [
    # Navigation
    ("up", "Up", "mdi:arrow-up", "KEY_UP", True),
    ("down", "Down", "mdi:arrow-down", "KEY_DOWN", True),
    ("left", "Left", "mdi:arrow-left", "KEY_LEFT", True),
    ("right", "Right", "mdi:arrow-right", "KEY_RIGHT", True),
    ("ok", "OK", "mdi:checkbox-blank-circle", "KEY_OK", True),
    ("back", "Back", "mdi:arrow-u-left-top", "KEY_BACK", True),
    ("menu", "Menu", "mdi:menu", "KEY_MENU", True),
    ("home", "Home", "mdi:home", "KEY_HOME", True),
    ("exit", "Exit", "mdi:close-box", "KEY_EXIT", True),
    # Channel
    ("channel_up", "Channel Up", "mdi:arrow-up-bold", "KEY_CHANNEL_UP", True),
    ("channel_down", "Channel Down", "mdi:arrow-down-bold", "KEY_CHANNEL_DOWN", True),
    # Playback
    ("play", "Play", "mdi:play", "KEY_PLAY", True),
    ("pause", "Pause", "mdi:pause", "KEY_PAUSE", True),
    ("stop", "Stop", "mdi:stop", "KEY_STOP", True),
    ("fast_forward", "Fast Forward", "mdi:fast-forward", "KEY_FAST_FORWARD", True),
    ("rewind", "Rewind", "mdi:rewind", "KEY_REWIND", True),
    # Info
    ("info", "Info", "mdi:information", "KEY_INFO", True),
    # Color buttons (disabled by default)
    ("red", "Red", "mdi:card", "KEY_RED", False),
    ("green", "Green", "mdi:card", "KEY_GREEN", False),
    ("yellow", "Yellow", "mdi:card", "KEY_YELLOW", False),
    ("blue", "Blue", "mdi:card", "KEY_BLUE", False),
    # Number buttons (disabled by default)
    ("0", "0", "mdi:numeric-0", "KEY_0", False),
    ("1", "1", "mdi:numeric-1", "KEY_1", False),
    ("2", "2", "mdi:numeric-2", "KEY_2", False),
    ("3", "3", "mdi:numeric-3", "KEY_3", False),
    ("4", "4", "mdi:numeric-4", "KEY_4", False),
    ("5", "5", "mdi:numeric-5", "KEY_5", False),
    ("6", "6", "mdi:numeric-6", "KEY_6", False),
    ("7", "7", "mdi:numeric-7", "KEY_7", False),
    ("8", "8", "mdi:numeric-8", "KEY_8", False),
    ("9", "9", "mdi:numeric-9", "KEY_9", False),
    # Extras (disabled by default)
    ("subtitle", "Subtitle", "mdi:subtitles", "KEY_SUBTITLE", False),
    ("power", "Power", "mdi:power", "KEY_POWER", True),
]
