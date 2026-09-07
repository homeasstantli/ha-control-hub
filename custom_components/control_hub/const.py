"""Constants for the Control Hub integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "control_hub"

# Config entry keys
CONF_HUB_KEY = "hub_key"
CONF_PROJECT_ID = "project_id"
CONF_API_KEY = "api_key"
CONF_DATABASE_URL = "database_url"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_UID = "uid"
CONF_FIRESTORE_PATH = "firestore_path"
CONF_RTDB_PATH = "rtdb_path"

# Defaults
DEFAULT_FIRESTORE_PATH = "hubs/{hub_key}/data/config"
DEFAULT_RTDB_PATH = "hubs/{hub_key}/state"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)
MIN_HUB_KEY_LENGTH = 12

# Google Identity / token endpoints
SIGNUP_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signUp"
SECURE_TOKEN_URL = "https://securetoken.googleapis.com/v1/token"
FIRESTORE_BASE = "https://firestore.googleapis.com/v1"

# Services
SERVICE_SET_CONFIG = "set_config"
SERVICE_PUSH_DATA = "push_data"
SERVICE_CREATE_PAIRING_CODE = "create_pairing_code"
ATTR_PATH = "path"
ATTR_DATA = "data"
ATTR_TARGET = "target"  # "firestore" | "rtdb"

# Local pairing (GitHub Pages website -> Home Assistant API)
PAIR_VIEW_URL = "/api/control_hub/pair"
DATA_PAIRING_CODES = "pairing_codes"
PAIRING_CODE_TTL = 300  # seconds
PAIRING_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
PAIRING_CODE_LENGTH = 8
WEB_USER_NAME = "Control Hub Web"
WEB_USER_STORAGE_KEY = f"{DOMAIN}.web_user"
