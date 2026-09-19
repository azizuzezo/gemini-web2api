"""OpenAPI 3.0 spec + Swagger UI page, served at /openapi.json and /docs."""

from . import __version__
from .models import MODELS


def build_openapi_spec() -> dict:
    """Build an OpenAPI 3.0 spec describing every endpoint, served at /openapi.json
    and rendered as interactive, testable docs at /docs (Swagger UI)."""
    model_ids = list(MODELS.keys())

    error_schema = {
        "type": "object",
        "properties": {
            "error": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
            }
        },
    }
    chat_message_schema = {
        "type": "object",
        "required": ["role", "content"],
        "properties": {
            "role": {"type": "string", "enum": ["system", "user", "assistant", "tool"]},
            "content": {"type": "string"},
        },
    }
    chat_request_schema = {
        "type": "object",
        "required": ["messages"],
        "properties": {
            "model": {
                "type": "string",
                "description": "Model id. Append `@think=N` (0=deepest..4=shallowest) to override thinking depth.",
                "enum": model_ids,
                "default": "gemini-3.5-flash",
            },
            "messages": {"type": "array", "items": chat_message_schema},
            "stream": {"type": "boolean", "default": False, "description": "Server-Sent Events streaming."},
            "tools": {"type": "array", "items": {"type": "object"}, "description": "OpenAI-style function tool definitions."},
            "tool_choice": {"description": "\"auto\", \"none\", or a specific tool object.", "default": "auto"},
        },
        "example": {
            "model": "gemini-3.5-flash",
            "messages": [{"role": "user", "content": "Hello!"}],
        },
    }
    chat_response_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "object": {"type": "string", "example": "chat.completion"},
            "created": {"type": "integer"},
            "model": {"type": "string"},
            "choices": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "message": {
                            "type": "object",
                            "properties": {
                                "role": {"type": "string"},
                                "content": {"type": "string", "nullable": True},
                                "tool_calls": {"type": "array", "items": {"type": "object"}},
                            },
                        },
                        "finish_reason": {"type": "string"},
                    },
                },
            },
            "usage": {
                "type": "object",
                "properties": {
                    "prompt_tokens": {"type": "integer"},
                    "completion_tokens": {"type": "integer"},
                    "total_tokens": {"type": "integer"},
                },
            },
        },
    }
    image_request_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "model": {"type": "string", "default": "imagen-3.0-generate-002", "enum": [m for m in model_ids if MODELS[m].get("is_image")] or model_ids},
            "prompt": {"type": "string"},
            "response_format": {"type": "string", "enum": ["url", "b64_json"], "default": "url"},
        },
        "example": {
            "model": "imagen-3.0-generate-002",
            "prompt": "A beautiful sunset over snowy mountains",
        },
    }
    image_response_schema = {
        "type": "object",
        "properties": {
            "created": {"type": "integer"},
            "data": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}, "b64_json": {"type": "string"}},
                },
            },
        },
    }
    models_list_schema = {
        "type": "object",
        "properties": {
            "object": {"type": "string", "example": "list"},
            "data": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "object": {"type": "string"},
                        "created": {"type": "integer"},
                        "owned_by": {"type": "string"},
                        "description": {"type": "string"},
                    },
                },
            },
        },
    }
    responses_request_schema = {
        "type": "object",
        "properties": {
            "model": {"type": "string", "enum": model_ids, "default": "gemini-3.5-flash"},
            "input": {"description": "A string, or an array of Responses-API input items.", "example": "Hello!"},
            "instructions": {"type": "string"},
            "tools": {"type": "array", "items": {"type": "object"}},
            "tool_choice": {"default": "auto"},
            "stream": {"type": "boolean", "default": False},
        },
        "example": {"model": "gemini-3.5-flash", "input": "Hello!"},
    }
    responses_response_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "object": {"type": "string", "example": "response"},
            "created_at": {"type": "integer"},
            "status": {"type": "string"},
            "model": {"type": "string"},
            "output": {"type": "array", "items": {"type": "object"}},
            "usage": {"type": "object"},
        },
    }
    google_models_list_schema = {
        "type": "object",
        "properties": {
            "models": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "displayName": {"type": "string"},
                        "description": {"type": "string"},
                        "supportedGenerationMethods": {"type": "array", "items": {"type": "string"}},
                    },
                },
            }
        },
    }
    google_generate_request_schema = {
        "type": "object",
        "required": ["contents"],
        "properties": {
            "contents": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string"},
                        "parts": {"type": "array", "items": {"type": "object", "properties": {"text": {"type": "string"}}}},
                    },
                },
            },
            "tools": {"type": "array", "items": {"type": "object"}},
            "toolConfig": {"type": "object"},
        },
        "example": {"contents": [{"role": "user", "parts": [{"text": "Hello!"}]}]},
    }
    google_generate_response_schema = {
        "type": "object",
        "properties": {
            "candidates": {"type": "array", "items": {"type": "object"}},
            "usageMetadata": {"type": "object"},
            "modelVersion": {"type": "string"},
        },
    }

    def json_body(schema):
        return {"content": {"application/json": {"schema": schema}}}

    def json_response(desc, schema):
        return {"description": desc, "content": {"application/json": {"schema": schema}}}

    error_response = json_response("Error", error_schema)
    auth_security = [{"bearerAuth": []}, {"apiKeyHeader": []}]

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "DuaCincin",
            "version": __version__,
        },
        "servers": [{"url": "/", "description": "This server"}],
        "tags": [
            {"name": "OpenAI-compatible", "description": "Drop-in replacement for the OpenAI API."},
            {"name": "Codex CLI", "description": "OpenAI Responses API, used by OpenAI Codex CLI."},
            {"name": "Gemini CLI", "description": "Google's native Generative Language API shape."},
            {"name": "Meta", "description": "Health and status."},
        ],
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer", "description": "`Authorization: Bearer <key>` (only enforced if `api_keys` is set in config)."},
                "apiKeyHeader": {"type": "apiKey", "in": "header", "name": "x-api-key", "description": "Alternative to Bearer auth."},
            },
            "schemas": {
                "Error": error_schema,
                "ChatCompletionRequest": chat_request_schema,
                "ChatCompletionResponse": chat_response_schema,
                "ImageGenerationRequest": image_request_schema,
                "ImageGenerationResponse": image_response_schema,
                "ModelsListResponse": models_list_schema,
                "ResponsesRequest": responses_request_schema,
                "ResponsesResponse": responses_response_schema,
                "GoogleModelsListResponse": google_models_list_schema,
                "GoogleGenerateContentRequest": google_generate_request_schema,
                "GoogleGenerateContentResponse": google_generate_response_schema,
            },
        },
        "paths": {
            "/": {
                "get": {
                    "tags": ["Meta"],
                    "summary": "Health check",
                    "responses": {"200": json_response("Server status", {"type": "object", "properties": {
                        "status": {"type": "string"}, "version": {"type": "string"}, "models": {"type": "array", "items": {"type": "string"}}}})},
                }
            },
            "/v1/models": {
                "get": {
                    "tags": ["OpenAI-compatible"],
                    "summary": "List available models",
                    "security": auth_security,
                    "responses": {"200": json_response("List of models", models_list_schema)},
                }
            },
            "/v1/chat/completions": {
                "post": {
                    "tags": ["OpenAI-compatible"],
                    "summary": "Chat completion",
                    "description": "OpenAI-compatible chat completions endpoint. Supports streaming (SSE) and function/tool calling.",
                    "security": auth_security,
                    "requestBody": {"required": True, **json_body(chat_request_schema)},
                    "responses": {
                        "200": json_response("Chat completion (or SSE stream when `stream: true`)", chat_response_schema),
                        "400": error_response,
                        "401": error_response,
                        "502": error_response,
                    },
                }
            },
            "/v1/images/generations": {
                "post": {
                    "tags": ["OpenAI-compatible"],
                    "summary": "Image generation",
                    "description": "OpenAI-compatible image generation, powered by Imagen 3. Requires a configured Google account cookie (`cookie_file`).",
                    "security": auth_security,
                    "requestBody": {"required": True, **json_body(image_request_schema)},
                    "responses": {
                        "200": json_response("Generated image(s)", image_response_schema),
                        "400": error_response,
                        "401": error_response,
                        "502": error_response,
                    },
                }
            },
            "/v1/responses": {
                "post": {
                    "tags": ["Codex CLI"],
                    "summary": "Responses API",
                    "description": "OpenAI Responses API shape, for OpenAI Codex CLI integration.",
                    "security": auth_security,
                    "requestBody": {"required": True, **json_body(responses_request_schema)},
                    "responses": {
                        "200": json_response("Response object (or SSE stream when `stream: true`)", responses_response_schema),
                        "400": error_response,
                        "401": error_response,
                        "502": error_response,
                    },
                }
            },
            "/v1beta/models": {
                "get": {
                    "tags": ["Gemini CLI"],
                    "summary": "List models (Google native shape)",
                    "security": auth_security,
                    "responses": {"200": json_response("List of models", google_models_list_schema)},
                }
            },
            "/v1beta/models/{model}:generateContent": {
                "post": {
                    "tags": ["Gemini CLI"],
                    "summary": "Generate content (non-streaming)",
                    "description": "Google Generative Language API compatible endpoint, used by Gemini CLI.",
                    "security": auth_security,
                    "parameters": [{"name": "model", "in": "path", "required": True, "schema": {"type": "string", "enum": model_ids}}],
                    "requestBody": {"required": True, **json_body(google_generate_request_schema)},
                    "responses": {
                        "200": json_response("Generated content", google_generate_response_schema),
                        "400": error_response,
                        "401": error_response,
                        "502": error_response,
                    },
                }
            },
            "/v1beta/models/{model}:streamGenerateContent": {
                "post": {
                    "tags": ["Gemini CLI"],
                    "summary": "Generate content (streaming, SSE)",
                    "description": "Google Generative Language API compatible streaming endpoint, used by Gemini CLI.",
                    "security": auth_security,
                    "parameters": [{"name": "model", "in": "path", "required": True, "schema": {"type": "string", "enum": model_ids}}],
                    "requestBody": {"required": True, **json_body(google_generate_request_schema)},
                    "responses": {
                        "200": json_response("SSE stream of generated content chunks", google_generate_response_schema),
                        "400": error_response,
                        "401": error_response,
                        "502": error_response,
                    },
                }
            },
        },
    }


DOCS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>DuaCincin &mdash; API Docs (Swagger UI)</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
  <style>body { margin: 0; background: #fafafa; }</style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
  <script>
    window.onload = function() {
      window.ui = SwaggerUIBundle({
        url: "/openapi.json",
        dom_id: "#swagger-ui",
        presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
        layout: "StandaloneLayout",
        deepLinking: true,
        tryItOutEnabled: true,
      });
    };
  </script>
</body>
</html>
"""
