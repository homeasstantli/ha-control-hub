"""Constants for the Control Hub integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "control_hub"

# Config entry keys
CONF_PAIRING_CODE = "pairing_code"
CONF_SETUP_URL = "setup_url"
CONF_HUB_ID = "hub_id"
CONF_PROJECT_ID = "project_id"
CONF_API_KEY = "api_key"
CONF_DATABASE_URL = "database_url"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_FIRESTORE_PATH = "firestore_path"
CONF_RTDB_PATH = "rtdb_path"

# Defaults
DEFAULT_FIRESTORE_PATH = "hubs/{hub_id}/config"
DEFAULT_RTDB_PATH = "hubs/{hub_id}/state"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)

# Google endpoints
IDENTITY_TOOLKIT_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken"
)
SECURE_TOKEN_URL = "https://securetoken.googleapis.com/v1/token"
FIRESTORE_BASE = "https://firestore.googleapis.com/v1"

# Services
SERVICE_SET_CONFIG = "set_config"
SERVICE_PUSH_DATA = "push_data"
ATTR_PATH = "path"
ATTR_DATA = "data"
ATTR_TARGET = "target"  # "firestore" | "rtdb"
