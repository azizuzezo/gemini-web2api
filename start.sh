#!/bin/sh
set -e

python - <<'PY'
import json
import os

config_path = "/app/config.json"
runtime_path = "/app/config.runtime.json"

with open(config_path, "r", encoding="utf-8") as f:
    config = json.load(f)

# Railway networking
config["host"] = "0.0.0.0"
config["port"] = int(os.environ.get("PORT", "8081"))

# API keys from Railway Variables
api_keys = os.environ.get("API_KEYS", "").strip()

if api_keys:
    config["api_keys"] = [
        key.strip()
        for key in api_keys.split(",")
        if key.strip()
    ]
else:
    config["api_keys"] = []

# Default model
config["default_model"] = os.environ.get(
    "DEFAULT_MODEL",
    "gemini-3.6-flash"
)

# Logging
config["log_requests"] = (
    os.environ.get("LOG_REQUESTS", "true").lower() == "true"
)

# Temporary chat option
config["temporary_chats"] = (
    os.environ.get("TEMPORARY_CHATS", "false").lower() == "true"
)

# Optional proxy
proxy = os.environ.get("HTTPS_PROXY", "").strip()

if proxy:
    config["proxy"] = proxy

with open(runtime_path, "w", encoding="utf-8") as f:
    json.dump(config, f)

print("Runtime config generated")
print("Port:", config["port"])
print("Model:", config["default_model"])
print("API Keys:", len(config["api_keys"]))
PY

exec python -m gemini_web2api \
    --config /app/config.runtime.json \
    --port "${PORT:-8081}"
