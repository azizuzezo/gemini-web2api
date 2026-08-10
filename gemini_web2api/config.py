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


def parse_env_api_keys():
    env_keys = os.environ.get("API_KEYS") or os.environ.get("API_KEY")
    if not env_keys:
        return []
    env_keys = env_keys.strip()
    if env_keys.startswith("["):
        try:
            parsed = json.loads(env_keys)
            if isinstance(parsed, list):
                return [str(k).strip() for k in parsed if str(k).strip()]
        except Exception:
            pass
    return [k.strip() for k in env_keys.split(",") if k.strip()]


def load_config(path: str = None):
    """Load config from JSON file."""
    if path and os.path.exists(path):
        with open(path) as f:
            CONFIG.update(json.load(f))
    if os.environ.get("PORT"):
        try:
            CONFIG["port"] = int(os.environ["PORT"])
        except ValueError:
            pass
    env_keys = parse_env_api_keys()
    if env_keys:
        CONFIG["api_keys"] = env_keys
    return CONFIG


if os.environ.get("PORT"):
    try:
        CONFIG["port"] = int(os.environ["PORT"])
    except ValueError:
        pass
env_keys = parse_env_api_keys()
if env_keys:
    CONFIG["api_keys"] = env_keys


def find_config():
    """Search for config file in standard locations."""
    for p in ["./config.json", os.path.expanduser("~/.config/gemini-web2api/config.json")]:
        if os.path.exists(p):
            return p
    return None

