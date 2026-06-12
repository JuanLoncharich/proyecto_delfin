# Credentials and LLM Provider Configuration

## Quick start

```bash
cp .env.example .env
# Edit .env — set these four values:
#   LLM_API_KEY     = your API key
#   LLM_BASE_URL    = provider's base URL (e.g. https://api.openai.com/v1)
#   PROVIDER_NAME   = provider identifier (e.g. "openai", "anthropic", "gemini")
#   LLM_MODEL       = default model name (e.g. "gpt-4o", "claude-sonnet-4-20250514")
```

## LLM provider variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `LLM_API_KEY` | Yes | — | API key for all LLM calls (OpenCode agents + planner) |
| `LLM_BASE_URL` | Yes | — | Base URL for the LLM provider's chat completions API (e.g. `https://api.openai.com/v1`) |
| `PROVIDER_NAME` | Yes | `openai` | Provider identifier for OpenCode auth.json |
| `LLM_MODEL` | No | `gpt-4o` | Default model for all OpenCode agents |

### Common provider values

| Provider | `PROVIDER_NAME` | `LLM_BASE_URL` |
|---|---|---|
| OpenAI | `openai` | `https://api.openai.com/v1` |
| Anthropic | `anthropic` | `https://api.anthropic.com/v1` |
| Google Gemini | `gemini` | `https://generativelanguage.googleapis.com/v1beta/openai` |
| e-INFRA CZ | `openai` | `https://llm.ai.e-infra.cz/v1` |
| OpenRouter | `openai` | `https://openrouter.ai/api/v1` |

For providers with a `/v1/chat/completions` endpoint (e-INFRA, OpenRouter, local proxies), use `PROVIDER_NAME=openai`.

### Per-agent model overrides

Each agent can use a different model. Leave empty to use `LLM_MODEL`:

| Variable | Agent | Default |
|---|---|---|
| `CODER56_MODEL` | Attacker (coder56) | `LLM_MODEL` |
| `DB_ADMIN_MODEL` | Benign traffic (db_admin) | `LLM_MODEL` |
| `SOC_GOD_MODEL` | Defender execution (soc_god) | `LLM_MODEL` |

### Planner-specific overrides

The defender's incident planner can use a different key/endpoint:

| Variable | Default | Description |
|---|---|---|
| `PLANNER_MODEL` | `gpt-4o` | Model for the incident response planner |
| `PLANNER_API_KEY` | `LLM_API_KEY` | API key override for the planner |
| `PLANNER_BASE_URL` | `LLM_BASE_URL` | Base URL override for the planner |

## SSH and lab credentials

These defaults are **for the isolated lab only**. Do not reuse them on real systems.

| Variable | Required | Default | Description |
|---|---|---|---|
| `SSH_COMPROMISED_PASS` | Yes | `admin` | SSH password for `labuser` on `lab_compromised` |
| `SSH_COMPROMISED_USER` | No | `labuser` | SSH username (changing requires image rebuild) |
| `LOGIN_USER` | No | `admin` | Web login app username on `lab_server` |
| `LOGIN_PASSWORD` | No | `admin` | Web login app password on `lab_server` |
| `DB_USER` | No | `labuser` | PostgreSQL user on `lab_server` |
| `DB_PASSWORD` | No | `labpass` | PostgreSQL password on `lab_server` |

## Hardcoded credentials

The `lab_server` root SSH password (`admin123`) is set directly in
`images/server/Dockerfile` and **cannot** be overridden via `.env`.
To change it, edit the Dockerfile and rebuild with `make build`.

## Backward compatibility

The old variable names `OPENCODE_API_KEY`, `OPENAI_API_KEY`, and `LLM_URL` still
work as fallbacks. `LLM_API_KEY` and `LLM_BASE_URL` take precedence if set.

## Testing LLM connectivity

### Via the config web app

```bash
make config
# Open http://localhost:8889 → LLM Provider section → "Test Connection"
```

### Via terminal (curl)

Load your `.env` and send a minimal request:

```bash
source .env && curl -s "${LLM_BASE_URL}/chat/completions" \
  -H "Authorization: Bearer ${LLM_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"'"${LLM_MODEL}"'","messages":[{"role":"user","content":"Reply with only the word: pong"}],"max_tokens":10}' \
  | python3 -m json.tool
```

Or with hardcoded values:

```bash
curl -s "https://your-provider-url/v1/chat/completions" \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"your-model","messages":[{"role":"user","content":"Reply with only the word: pong"}],"max_tokens":10}' \
  | python3 -m json.tool
```

A successful response returns a JSON object with `choices[0].message.content`. If you get a 401, check `LLM_API_KEY`. If you get a connection error, check `LLM_BASE_URL`.
