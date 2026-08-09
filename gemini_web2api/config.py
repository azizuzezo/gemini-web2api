"""Configuration management."""

import json
import os

DEFAULT_CONFIG = {
    "port": 8081,
    "host": "0.0.0.0",
    "retry_attempts": 3,
    "retry_delay_sec": 2,
    "request_timeout_sec": 180,
    "gemini_bl": "boq_assistant-bard-web-server_20260716.08_p0",
    "auth_user": None,
    "xsrf_token": None,
    "default_model": "gemini-3.6-flash",
    "log_requests": True,
    "cookie_file": None,
    "proxy": None,
    "api_keys": [],
}

CONFIG = dict(DEFAULT_CONFIG)


def load_config(path: str = None):
    """Load config from JSON and override with environment variables."""

    # Load config.json terlebih dahulu
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            CONFIG.update(json.load(f))

    # ==========================================
    # RAILWAY ENVIRONMENT VARIABLES
    # ==========================================

    # API_KEYS=key1,key2,key3
    env_api_keys = os.environ.get("API_KEYS", "").strip()

    if env_api_keys:
        CONFIG["api_keys"] = [
            key.strip()
            for key in env_api_keys.split(",")
            if key.strip()
        ]

    # Railway PORT
    env_port = os.environ.get("PORT", "").strip()

    if env_port:
        try:
            CONFIG["port"] = int(env_port)
        except ValueError:
            pass

    # Default model
    env_model = os.environ.get("DEFAULT_MODEL", "").strip()

    if env_model:
        CONFIG["default_model"] = env_model

    # Optional proxy
    env_proxy = os.environ.get("HTTPS_PROXY", "").strip()

    if env_proxy:
        CONFIG["proxy"] = env_proxy

    return CONFIG


def find_config():
    """Search for config file in standard locations."""

    for p in [
        "./config.json",
        os.path.expanduser("~/.config/gemini-web2api/config.json"),
    ]:
        if os.path.exists(p):
            return p

    return None
