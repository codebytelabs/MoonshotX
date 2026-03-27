"""
emergentintegrations shim — multi-provider LLM client.

Supported providers (set via LLM_PROVIDER env var or with_model(provider, model)):
  - "openrouter"  : OpenRouter API (https://openrouter.ai/api/v1)
  - "ollama"      : Ollama Cloud   (OLLAMA_BASE_URL + /v1/chat/completions)

Switch at runtime by changing LLM_PROVIDER in .env and restarting.
"""
import asyncio
import logging
import os
from dataclasses import dataclass

import requests as _req

logger = logging.getLogger("emergentintegrations.llm.chat")

# Legacy model name aliases → OpenRouter IDs
_OPENROUTER_MODEL_MAP = {
    "claude-haiku-4-5-20251001":   "anthropic/claude-haiku-4-5",
    "claude-4-sonnet-20250514":    "anthropic/claude-sonnet-4-5",
    "claude-3-haiku-20240307":     "anthropic/claude-3-haiku",
    "claude-3-5-haiku-20241022":   "anthropic/claude-haiku-4-5",
    "claude-3-7-sonnet-20250219":  "anthropic/claude-sonnet-4-5",
    "gpt-4o":                      "openai/gpt-4o",
    "gpt-4o-mini":                 "openai/gpt-4o-mini",
}

_DEFAULT_QUICK = "google/gemini-2.5-flash-lite-preview-09-2025"
_DEFAULT_DEEP  = "anthropic/claude-haiku-4-5"


@dataclass
class UserMessage:
    text: str


class LlmChat:
    def __init__(self, api_key: str, session_id: str, system_message: str = "", max_tokens: int = 1024):
        self._api_key = api_key
        self._session_id = session_id
        self._system_message = system_message
        self._provider = os.getenv("LLM_PROVIDER", "openrouter").lower()
        self._model = _DEFAULT_QUICK
        self._max_tokens = max_tokens

    def with_model(self, provider: str, model: str) -> "LlmChat":
        self._provider = provider.lower()
        if self._provider == "openrouter":
            self._model = _OPENROUTER_MODEL_MAP.get(model, model)
        else:
            self._model = model   # Ollama model names passed through as-is
        return self

    async def send_message(self, message: UserMessage) -> str:
        return await asyncio.to_thread(self._send_sync, message.text)

    def _build_messages(self, user_text: str) -> list:
        msgs = []
        if self._system_message:
            msgs.append({"role": "system", "content": self._system_message})
        msgs.append({"role": "user", "content": user_text})
        return msgs

    def _send_sync(self, user_text: str) -> str:
        if self._provider == "ollama":
            return self._send_ollama(user_text)
        return self._send_openrouter(user_text)

    # ── OpenRouter ────────────────────────────────────────────────────────────
    def _send_openrouter(self, user_text: str) -> str:
        api_key = os.getenv("OPENROUTER_API_KEY", self._api_key)
        base    = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
        model   = self._model
        if "/" not in model:
            model = _OPENROUTER_MODEL_MAP.get(model, f"openai/{model}")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://moonshotx.ai",
            "X-Title": "MoonshotX",
        }
        payload = {
            "model": model,
            "messages": self._build_messages(user_text),
            "max_tokens": self._max_tokens,
            "temperature": 0.1,
        }
        try:
            r = _req.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=60)
            r.raise_for_status()
            return r.json()["choices"][0]["message"].get("content") or ""
        except Exception as e:
            logger.error(f"OpenRouter call failed (model={model}): {e}")
            raise

    # ── Ollama Cloud ──────────────────────────────────────────────────────────
    def _send_ollama(self, user_text: str) -> str:
        api_key = os.getenv("OLLAMA_API_KEY", "")
        base    = os.getenv("OLLAMA_BASE_URL", "https://ollama.com/api").rstrip("/")
        model   = self._model

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": self._build_messages(user_text),
            "max_tokens": self._max_tokens,
            "temperature": 0.1,
            "stream": False,
        }

        # Try OpenAI-compatible endpoint first, then native Ollama format
        endpoints = [
            (f"{base}/v1/chat/completions", "openai"),
            (f"{base}/chat",               "native"),
        ]
        last_err = None
        for url, fmt in endpoints:
            try:
                r = _req.post(url, headers=headers, json=payload, timeout=90)
                r.raise_for_status()
                data = r.json()
                if fmt == "openai":
                    return data["choices"][0]["message"].get("content") or ""
                else:
                    return data.get("message", {}).get("content") or ""
            except Exception as e:
                logger.debug(f"Ollama {fmt} endpoint failed ({url}): {e}")
                last_err = e
                continue

        logger.error(f"All Ollama endpoints failed (model={model}): {last_err}")
        raise RuntimeError(f"Ollama call failed: {last_err}")
