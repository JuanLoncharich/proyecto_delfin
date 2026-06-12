"""Trident Config — FastAPI backend for managing .env settings."""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("config")

ENV_PATH = Path(os.getenv("ENV_PATH", "/app/.env"))

# ── Schema: defines every variable the UI can edit ──────────────────
VARIABLE_SCHEMA: list[dict[str, Any]] = [
    # -- LLM Provider --
    {
        "key": "LLM_API_KEY",
        "label": "API Key",
        "group": "provider",
        "type": "password",
        "required": True,
        "description": "API key for the LLM provider. Shared across all agents unless overridden.",
    },
    {
        "key": "LLM_BASE_URL",
        "label": "Base URL",
        "group": "provider",
        "type": "text",
        "required": True,
        "placeholder": "https://api.openai.com/v1",
        "description": "Base URL for the LLM provider's chat completions API.",
    },
    {
        "key": "PROVIDER_NAME",
        "label": "Provider Name",
        "group": "provider",
        "type": "text",
        "required": True,
        "placeholder": "openai",
        "description": "Provider identifier for OpenCode auth. Use 'openai' for providers with a /v1/chat/completions endpoint (most providers). Use 'gemini' for Google, 'anthropic' for Anthropic.",
    },
    {
        "key": "LLM_MODEL",
        "label": "Default Model",
        "group": "provider",
        "type": "text",
        "required": False,
        "default": "gpt-4o",
        "description": "Default model for all OpenCode agents.",
    },
    # -- Per-agent models --
    {
        "key": "CODER56_MODEL",
        "label": "Coder56 (Attacker)",
        "group": "agents",
        "type": "text",
        "required": False,
        "placeholder": "gpt-4o",
        "description": "Model for the attacker agent. Leave empty to use the default model.",
    },
    {
        "key": "DB_ADMIN_MODEL",
        "label": "DB Admin (Benign)",
        "group": "agents",
        "type": "text",
        "required": False,
        "placeholder": "gpt-4o",
        "description": "Model for the benign traffic agent. Leave empty to use the default model.",
    },
    {
        "key": "SOC_GOD_MODEL",
        "label": "SOC God (Defender)",
        "group": "agents",
        "type": "text",
        "required": False,
        "placeholder": "gpt-4o",
        "description": "Model for the defender execution agent. Leave empty to use the default model.",
    },
    # -- Planner --
    {
        "key": "PLANNER_MODEL",
        "label": "Planner Model",
        "group": "planner",
        "type": "text",
        "required": False,
        "default": "gpt-4o",
        "description": "Model for the incident response planner (defender).",
    },
    {
        "key": "PLANNER_API_KEY",
        "label": "Planner API Key",
        "group": "planner",
        "type": "password",
        "required": False,
        "placeholder": "defaults to main API key",
        "description": "Separate API key for the planner. Leave empty to use the main API key.",
    },
    {
        "key": "PLANNER_BASE_URL",
        "label": "Planner Base URL",
        "group": "planner",
        "type": "text",
        "required": False,
        "placeholder": "defaults to main base URL",
        "description": "Separate base URL for the planner. Leave empty to use the main base URL.",
    },
    # -- Defender --
    {
        "key": "DEFENDER_PORT",
        "label": "Defender Port",
        "group": "defender",
        "type": "text",
        "required": False,
        "default": "8000",
        "description": "Host port for the defender health endpoint.",
    },
    {
        "key": "OPENCODE_TIMEOUT",
        "label": "OpenCode Timeout (s)",
        "group": "defender",
        "type": "text",
        "required": False,
        "default": "1200",
        "description": "Seconds before an OpenCode agent session is forcibly terminated.",
    },
    # -- Lab credentials --
    {
        "key": "SSH_COMPROMISED_PASS",
        "label": "SSH Password",
        "group": "lab",
        "type": "password",
        "required": True,
        "description": "SSH password for labuser on the compromised host.",
    },
    {
        "key": "LOGIN_USER",
        "label": "Web Login User",
        "group": "lab",
        "type": "text",
        "required": False,
        "default": "admin",
        "description": "Username for the web login app on the server.",
    },
    {
        "key": "LOGIN_PASSWORD",
        "label": "Web Login Password",
        "group": "lab",
        "type": "password",
        "required": False,
        "default": "admin",
        "description": "Password for the web login app on the server.",
    },
    {
        "key": "DB_USER",
        "label": "PostgreSQL User",
        "group": "lab",
        "type": "text",
        "required": False,
        "default": "labuser",
        "description": "PostgreSQL username on the server.",
    },
    {
        "key": "DB_PASSWORD",
        "label": "PostgreSQL Password",
        "group": "lab",
        "type": "password",
        "required": False,
        "default": "labpass",
        "description": "PostgreSQL password on the server.",
    },
]

GROUPS = [
    {"id": "provider", "title": "LLM Provider", "description": "Main API key, base URL, and provider settings."},
    {"id": "agents", "title": "Agent Models", "description": "Per-agent model overrides. Leave empty to use the default model."},
    {"id": "planner", "title": "Planner", "description": "Incident response planner settings. Overrides main provider if set."},
    {"id": "defender", "title": "Defender", "description": "Defender and OpenCode session settings."},
    {"id": "lab", "title": "Lab Credentials", "description": "SSH, web login, and database credentials."},
]

PROVIDER_PRESETS = {
    "openai": {
        "LLM_BASE_URL": "https://api.openai.com/v1",
        "PROVIDER_NAME": "openai",
    },
    "anthropic": {
        "LLM_BASE_URL": "https://api.anthropic.com/v1",
        "PROVIDER_NAME": "anthropic",
    },
    "gemini": {
        "LLM_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai",
        "PROVIDER_NAME": "gemini",
    },
    "einfra": {
        "LLM_BASE_URL": "https://llm.ai.e-infra.cz/v1",
        "PROVIDER_NAME": "openai",
    },
    "openrouter": {
        "LLM_BASE_URL": "https://openrouter.ai/api/v1",
        "PROVIDER_NAME": "openai",
    },
}


app = FastAPI(title="Trident Config", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ──────────────────────────────────────────────────────────

def _read_env() -> dict[str, str | None]:
    """Read .env file, returning all key-value pairs (values may be None)."""
    if ENV_PATH.exists():
        return dict(dotenv_values(ENV_PATH))
    return {}


def _write_env(updates: dict[str, str | None]) -> None:
    """Write updates to .env, preserving comments and ordering."""
    lines: list[str] = []
    existing_keys: set[str] = set()

    if ENV_PATH.exists():
        raw = ENV_PATH.read_text(encoding="utf-8")
        for line in raw.splitlines():
            stripped = line.strip()
            # Comment or blank
            if not stripped or stripped.startswith("#"):
                lines.append(line)
                continue
            # KEY=VALUE
            match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)", stripped)
            if match:
                key = match.group(1)
                existing_keys.add(key)
                if key in updates:
                    val = updates[key]
                    if val is None or val == "":
                        lines.append(f"{key}=")
                    else:
                        lines.append(f"{key}={val}")
                    del updates[key]
                else:
                    lines.append(line)
            else:
                lines.append(line)

    # Append any new keys
    for key, val in updates.items():
        if val is None or val == "":
            lines.append(f"{key}=")
        else:
            lines.append(f"{key}={val}")

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── API ──────────────────────────────────────────────────────────────

class EnvUpdate(BaseModel):
    values: dict[str, str | None]


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/schema")
async def schema():
    """Return the full schema: groups, variables, and presets."""
    return {
        "groups": GROUPS,
        "variables": VARIABLE_SCHEMA,
        "presets": PROVIDER_PRESETS,
    }


@app.get("/api/env")
async def read_env():
    """Read current .env values."""
    env = _read_env()
    # Mask API keys for security (show only last 4 chars)
    masked = {}
    for var in VARIABLE_SCHEMA:
        key = var["key"]
        val = env.get(key, "")
        if val and var.get("type") == "password" and key != "SSH_COMPROMISED_PASS":
            if len(val) > 8:
                masked[key] = "*" * (len(val) - 4) + val[-4:]
            else:
                masked[key] = "****"
        else:
            masked[key] = val or ""
    return {"values": masked}


@app.post("/api/env")
async def write_env(update: EnvUpdate):
    """Write .env values. Empty string clears the variable."""
    _write_env(update.values)
    return {"status": "ok"}


@app.get("/api/validate")
async def validate_env():
    """Check if required variables are set."""
    env = _read_env()
    missing = []
    for var in VARIABLE_SCHEMA:
        if var.get("required"):
            val = env.get(var["key"], "")
            if not val:
                missing.append(var["key"])
    return {"valid": len(missing) == 0, "missing": missing}


@app.post("/api/test-connection")
async def test_connection():
    """Send a minimal request to the LLM provider to verify connectivity."""
    import json

    env = _read_env()
    api_key = env.get("LLM_API_KEY", "")
    base_url = env.get("LLM_BASE_URL", "")
    model = env.get("LLM_MODEL", "gpt-4o")

    if not api_key:
        return {"success": False, "error": "LLM_API_KEY is not set."}
    if not base_url:
        return {"success": False, "error": "LLM_BASE_URL is not set."}

    # Normalize base URL
    base_url = base_url.rstrip("/")
    url = f"{base_url}/chat/completions"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with only the word: pong"}],
        "max_tokens": 10,
        "temperature": 0,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            elapsed = round(time.time() - start, 2)

            if resp.status_code == 200:
                data = resp.json()
                reply = ""
                choices = data.get("choices", [])
                if choices:
                    reply = choices[0].get("message", {}).get("content", "").strip()
                model_used = data.get("model", model)
                return {
                    "success": True,
                    "reply": reply,
                    "model": model_used,
                    "latency_s": elapsed,
                }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {resp.status_code}: {resp.text[:500]}",
                    "latency_s": elapsed,
                }

    except httpx.TimeoutException:
        return {"success": False, "error": "Request timed out (30s)."}
    except httpx.ConnectError:
        return {"success": False, "error": f"Connection failed. Check LLM_BASE_URL: {base_url}"}
    except Exception as e:
        return {"success": False, "error": str(e)[:500]}


# ── Serve React static build (production) ────────────────────────────
_static_dir = Path(__file__).parent.parent / "frontend" / "dist"
if _static_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_static_dir / "assets")), name="static-assets")

    _index_html = _static_dir / "index.html"

    @app.get("/{full_path:path}")
    async def spa_fallback(request: Request, full_path: str):
        static_file = _static_dir / full_path
        if full_path and static_file.is_file():
            return FileResponse(str(static_file))
        return FileResponse(str(_index_html))
