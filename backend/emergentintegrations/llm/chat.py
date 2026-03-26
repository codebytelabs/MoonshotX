"""
emergentintegrations shim — routes LLM calls through OpenRouter (OpenAI-compatible).

Provider resolution order:
  1. If provider == "openrouter" → use OpenRouter directly
  2. If OPENROUTER_API_KEY is set → route all calls through OpenRouter
  3. Fallback: try litellm with original provider
"""
import asyncio
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger("emergentintegrations.llm.chat")

# Default OpenRouter models mapped from pipeline model names
_OPENROUTER_MODEL_MAP = {
    # Legacy pipeline model names → OpenRouter equivalents
    "claude-haiku-4-5-20251001": "anthropic/claude-haiku-4-5",
    "claude-4-sonnet-20250514": "anthropic/claude-sonnet-4-5",
    "claude-3-haiku-20240307": "anthropic/claude-3-haiku",
    "claude-3-5-haiku-20241022": "anthropic/claude-haiku-4-5",
    "claude-3-7-sonnet-20250219": "anthropic/claude-sonnet-4-5",
    "gpt-4o": "openai/gpt-4o",
    "gpt-4o-mini": "openai/gpt-4o-mini",
}

# Defaults if pipeline hasn't been updated yet
_DEFAULT_QUICK = "google/gemini-2.5-flash-lite-preview-09-2025"
_DEFAULT_DEEP = "anthropic/claude-haiku-4-5"


@dataclass
class UserMessage:
    text: str


class LlmChat:
    def __init__(self, api_key: str, session_id: str, system_message: str = "", max_tokens: int = 1024):
        self._api_key = api_key
        self._session_id = session_id
        self._system_message = system_message
        self._provider = "openrouter"
        self._model = _DEFAULT_QUICK
        self._max_tokens = max_tokens

    def with_model(self, provider: str, model: str) -> "LlmChat":
        self._provider = provider.lower()
        # Resolve model name through map; if already has "/" it's a full OpenRouter model id
        if "/" in model:
            self._model = model
        else:
            self._model = _OPENROUTER_MODEL_MAP.get(model, model)
        return self

    async def send_message(self, message: UserMessage) -> str:
        return await asyncio.to_thread(self._send_sync, message.text)

    def _send_sync(self, user_text: str) -> str:
        or_key = os.getenv("OPENROUTER_API_KEY", self._api_key)
        or_base = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

        messages = []
        if self._system_message:
            messages.append({"role": "system", "content": self._system_message})
        messages.append({"role": "user", "content": user_text})

        # Resolve final model id for OpenRouter
        model = self._model
        if "/" not in model:
            model = _OPENROUTER_MODEL_MAP.get(model, f"openai/{model}")

        try:
            import requests as _req
            headers = {
                "Authorization": f"Bearer {or_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://moonshotx.ai",
                "X-Title": "MoonshotX",
            }
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": self._max_tokens,
                "temperature": 0.1,
            }
            r = _req.post(
                f"{or_base.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"].get("content") or ""
        except Exception as e:
            logger.error(f"LLM call failed (model={model}): {e}")
            raise
