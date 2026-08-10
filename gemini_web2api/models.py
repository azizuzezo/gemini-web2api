"""Model definitions and mapping from Gemini frontend JS source."""

# MODE_CATEGORY enum from 028-6eb337387583.js:
#   1=FAST, 2=THINKING, 3=PRO, 4=AUTO, 5=FAST_DYNAMIC_THINKING, 6=FLASH_LITE

MODELS = {
    "gemini-3.6-flash": {
        "mode": 1, "think": 4,
        "desc": "Latest all-around model (Gemini 3.6 Flash)",
    },
    "gemini-3.5-flash": {
        "mode": 1, "think": 4,
        "desc": "Alias for gemini-3.6-flash (backend upgraded)",
    },
    "gemini-2.5-flash": {
        "mode": 1, "think": 4,
        "desc": "Gemini 2.5 Flash model",
    },
    "gemini-2.0-flash": {
        "mode": 1, "think": 4,
        "desc": "Gemini 2.0 Flash model",
    },
    "gemini-1.5-flash": {
        "mode": 1, "think": 4,
        "desc": "Gemini 1.5 Flash model",
    },
    "gemini-3.5-flash-thinking": {
        "mode": 2, "think": 0,
        "desc": "Deep thinking mode, longest output (~20k chars)",
    },
    "gemini-2.0-flash-thinking-exp": {
        "mode": 2, "think": 0,
        "desc": "Experimental thinking mode",
    },
    "gemini-3.1-pro": {
        "mode": 3, "think": 4,
        "desc": "Pro model (requires cookie for real routing)",
    },
    "gemini-1.5-pro": {
        "mode": 3, "think": 4,
        "desc": "Gemini 1.5 Pro model",
    },
    "gemini-3.1-pro-enhanced": {
        "mode": 3, "think": 4, "extra": {31: 2, 80: 3},
        "desc": "Pro with enhanced output (experimental)",
    },
    "gemini-auto": {
        "mode": 4, "think": 4,
        "desc": "Auto model selection",
    },
    "gemini-3.5-flash-thinking-lite": {
        "mode": 5, "think": 0,
        "desc": "Dynamic thinking with adaptive depth",
    },
    "gemini-flash-lite": {
        "mode": 6, "think": 4,
        "desc": "Lightweight fast model",
    },
    "imagen-3.0-generate-002": {
        "mode": 1, "think": 4, "is_image": True,
        "desc": "Imagen 3 Image Generation model",
    },
    "imagen-3": {
        "mode": 1, "think": 4, "is_image": True,
        "desc": "Alias for Imagen 3 Image Generation model",
    },
    "dall-e-3": {
        "mode": 1, "think": 4, "is_image": True,
        "desc": "OpenAI DALL-E 3 alias (routes to Imagen 3)",
    },
    "dall-e-2": {
        "mode": 1, "think": 4, "is_image": True,
        "desc": "OpenAI DALL-E 2 alias (routes to Imagen 3)",
    },
    "nano-banana": {
        "mode": 6, "think": 4,
        "desc": "Nano Banana lightweight fast model (Flash Lite alias)",
    },
    "nano_banana": {
        "mode": 6, "think": 4,
        "desc": "Alias for nano-banana",
    },
}


def resolve_model(model_name: str, default: str = "gemini-3.6-flash"):
    """Resolve model name to (name, mode_id, think_mode, error, extra_fields).

    Supports exact matches, @think=N overrides, and fuzzy fallback based on model keywords
    (imagen/dall-e/image -> Imagen 3, thinking/think -> Thinking mode, pro -> Pro mode, etc.).
    """
    if not model_name:
        model_name = default

    think_override = None
    if "@think=" in model_name:
        model_name, think_str = model_name.rsplit("@think=", 1)
        try:
            think_override = int(think_str)
        except ValueError:
            return None, None, None, f"Invalid think level: {think_str}", None

    cfg = MODELS.get(model_name)
    if not cfg:
        lower = model_name.lower()
        if any(k in lower for k in ("imagen", "dall-e", "image-gen", "image_gen")):
            matched = "imagen-3.0-generate-002"
        elif any(k in lower for k in ("nano", "banana")):
            matched = "nano-banana"
        elif "thinking" in lower or "think" in lower:
            matched = "gemini-3.5-flash-thinking"
        elif "pro" in lower:
            matched = "gemini-3.1-pro"
        elif "lite" in lower:
            matched = "gemini-flash-lite"
        elif "auto" in lower:
            matched = "gemini-auto"
        elif "flash" in lower:
            matched = "gemini-3.6-flash"
        else:
            matched = default

        from .gemini import log
        log(f"Model '{model_name}' mapped to '{matched}'")
        model_name = matched
        cfg = MODELS[matched]

    mode_id = cfg["mode"]
    think_mode = think_override if think_override is not None else cfg["think"]
    extra = cfg.get("extra")
    return model_name, mode_id, think_mode, None, extra

