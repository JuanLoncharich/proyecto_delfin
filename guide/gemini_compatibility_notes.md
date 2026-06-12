# Gemini Provider Compatibility Notes

> **Most issues below are now resolved by the template-based config system.**
> The entrypoint generates `opencode.json` and `auth.json` from environment
> variables at container start, so provider key mismatches and malformed
> configs are no longer possible — as long as your `.env` is correct.

---

## Setup for Gemini

```bash
# In .env:
LLM_API_KEY=your-gemini-api-key
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
PROVIDER_NAME=gemini
LLM_MODEL=gemini-2.5-flash
```

That's it. The entrypoint will generate `auth.json` with `"gemini"` as the
provider key and `opencode.json` with `gemini/gemini-2.5-flash` as the model.

---

## Historical issues (resolved by template)

These issues affected the old static `opencode.json` and are kept for reference.

### Problem 1: Unknown fields in JSON payload

Gemini's OpenAI-compatible endpoint strictly validates the JSON payload and
rejects unknown fields (`bash`, `edit`, `write` at the agent level).

**Status:** The template does not include these fields at the agent level.
They exist only in the `permission` block where Gemini accepts them.

### Problem 2: auth.json configured for wrong provider

The old entrypoint hardcoded `"gemini"` in `auth.json`. If the provider name
didn't match `opencode.json`, authentication failed silently.

**Status:** Both `auth.json` and `opencode.json` are now generated from the
same `PROVIDER_NAME` env var. They always match.

### Problem 3: Gemini 2.0 Flash quota exhaustion

`gemini-2.0-flash` has strict free-tier quota limits. Even a single test
request returns a 429 error.

**Status:** Set `LLM_MODEL=gemini-2.5-flash` in `.env` (more generous quota).
Per-agent overrides (`CODER56_MODEL`, etc.) can also use different models.

### Problem 4: Prompt split into multiple JSON keys

The old `opencode.json` had the db_admin prompt split across multiple JSON
keys instead of a single string. Gemini rejected the extra keys.

**Status:** The template has all prompts as single `\n`-separated strings.
