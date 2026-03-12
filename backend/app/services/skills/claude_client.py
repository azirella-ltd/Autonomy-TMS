"""
Thin Claude API client with vLLM/Qwen fallback.

Checks CLAUDE_API_KEY env var for Anthropic API access.
Falls back to existing vLLM/Qwen via LLM_API_BASE if not set.
Supports prompt caching for static SKILL.md instructions.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# Model identifiers
CLAUDE_HAIKU = "claude-haiku-4-5-20251001"
CLAUDE_SONNET = "claude-sonnet-4-6"

# Env var overrides
ENV_CLAUDE_API_KEY = "CLAUDE_API_KEY"
ENV_CLAUDE_MODEL_HAIKU = "CLAUDE_MODEL_HAIKU"
ENV_CLAUDE_MODEL_SONNET = "CLAUDE_MODEL_SONNET"
ENV_LLM_API_BASE = "LLM_API_BASE"
ENV_LLM_API_KEY = "LLM_API_KEY"
ENV_LLM_MODEL_NAME = "LLM_MODEL_NAME"


class ClaudeClient:
    """
    Unified LLM client that routes to Claude API or vLLM fallback.

    Usage:
        client = ClaudeClient()
        response = await client.complete(
            system_prompt="You are an ATP decision agent...",
            user_message=json.dumps(state_features),
            model_tier="haiku",
        )
    """

    def __init__(self, force_vllm: bool = False):
        self._claude_api_key = os.getenv(ENV_CLAUDE_API_KEY)
        self._llm_api_base = os.getenv(ENV_LLM_API_BASE)
        self._llm_api_key = os.getenv(ENV_LLM_API_KEY, "not-needed")
        self._llm_model_name = os.getenv(ENV_LLM_MODEL_NAME, "qwen3-8b")
        self._haiku_model = os.getenv(ENV_CLAUDE_MODEL_HAIKU, CLAUDE_HAIKU)
        self._sonnet_model = os.getenv(ENV_CLAUDE_MODEL_SONNET, CLAUDE_SONNET)
        self._http_client: Optional[httpx.AsyncClient] = None
        self._force_vllm = force_vllm  # bypass Anthropic API even if CLAUDE_API_KEY is set

    @property
    def uses_claude(self) -> bool:
        """Whether we're using Claude API (vs vLLM fallback)."""
        return bool(self._claude_api_key) and not self._force_vllm

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=120.0)
        return self._http_client

    def _resolve_model(self, model_tier: str) -> str:
        """Resolve model tier to actual model identifier."""
        if self.uses_claude:
            if model_tier == "haiku":
                return self._haiku_model
            return self._sonnet_model
        return self._llm_model_name

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        model_tier: str = "haiku",
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """
        Send a completion request to Claude API or vLLM fallback.

        Args:
            system_prompt: The SKILL.md content + RAG context
            user_message: JSON-encoded state features
            model_tier: "haiku" or "sonnet"
            temperature: Low for deterministic decisions
            max_tokens: Max response tokens

        Returns:
            dict with keys: content (str), model (str), tokens_used (int)
        """
        model = self._resolve_model(model_tier)
        start_time = time.monotonic()

        if self.uses_claude:
            result = await self._call_claude(
                system_prompt, user_message, model, temperature, max_tokens
            )
        elif self._llm_api_base:
            result = await self._call_vllm(
                system_prompt, user_message, model, temperature, max_tokens
            )
        else:
            raise RuntimeError(
                "No LLM backend configured. Set CLAUDE_API_KEY or LLM_API_BASE."
            )

        elapsed_ms = (time.monotonic() - start_time) * 1000
        logger.info(
            "Skill LLM call: model=%s, tokens=%d, latency=%.0fms",
            result["model"],
            result["tokens_used"],
            elapsed_ms,
        )
        return result

    async def _call_claude(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        """Call Anthropic Messages API with prompt caching."""
        client = await self._get_client()
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self._claude_api_key,
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "prompt-caching-2024-07-31",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": [
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                "messages": [{"role": "user", "content": user_message}],
            },
        )
        response.raise_for_status()
        data = response.json()
        content = data["content"][0]["text"] if data.get("content") else ""
        usage = data.get("usage", {})
        tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        return {"content": content, "model": model, "tokens_used": tokens}

    async def _call_vllm(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        """Call vLLM/Ollama via OpenAI-compatible API."""
        client = await self._get_client()
        base = self._llm_api_base.rstrip("/")
        response = await client.post(
            f"{base}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._llm_api_key}",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            },
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"] if data.get("choices") else ""
        usage = data.get("usage", {})
        tokens = usage.get("total_tokens", 0)
        return {"content": content, "model": model, "tokens_used": tokens}

    async def close(self):
        """Close the HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    def parse_json_response(self, content: str) -> dict[str, Any]:
        """
        Parse JSON from Claude's response, handling markdown code blocks.

        Claude sometimes wraps JSON in ```json ... ``` blocks.
        """
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines[1:] if not l.strip().startswith("```")]
            text = "\n".join(lines)
        return json.loads(text)
