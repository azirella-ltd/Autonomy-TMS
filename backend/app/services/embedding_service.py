"""
Embedding Service — Local and remote embedding generation for RAG

Calls OpenAI-compatible embedding endpoints (Ollama, vLLM, or OpenAI)
to generate vector embeddings for document chunks and search queries.

Default model: nomic-embed-text (768 dimensions, runs locally via Ollama)
"""

import logging
import os
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generate vector embeddings via OpenAI-compatible API.

    Works with Ollama, vLLM, or OpenAI — all expose /v1/embeddings.
    """

    def __init__(
        self,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.api_base = (
            api_base
            or os.getenv("EMBEDDING_API_BASE")
            or os.getenv("LLM_API_BASE")
            or "http://localhost:11434/v1"
        )
        self.model = model or os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "not-needed")
        self._url = f"{self.api_base.rstrip('/')}/embeddings"

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts and return their vector representations.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (each a list of floats).

        Raises:
            RuntimeError: If the embedding endpoint is unreachable or returns an error.
        """
        if not texts:
            return []

        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key != "not-needed":
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "input": texts,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(self._url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

                # OpenAI-compatible response format
                embeddings = [item["embedding"] for item in data["data"]]
                return embeddings

        except httpx.ConnectError:
            logger.warning(
                f"Embedding service unreachable at {self._url}. "
                "Ensure Ollama or vLLM is running."
            )
            raise RuntimeError(
                f"Embedding service unreachable at {self.api_base}. "
                "Start with: make up-llm-ollama && make ollama-pull-models"
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"Embedding API error: {e.response.status_code} — {e.response.text}")
            raise RuntimeError(f"Embedding API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise RuntimeError(f"Embedding failed: {e}")

    async def embed_query(self, query: str) -> List[float]:
        """Embed a single query string.

        Convenience wrapper around embed_texts for single-query use.
        """
        results = await self.embed_texts([query])
        return results[0]

    async def health_check(self) -> dict:
        """Check if the embedding service is reachable."""
        try:
            # Try a minimal embedding to verify the model is loaded
            await self.embed_texts(["health check"])
            return {
                "status": "ok",
                "api_base": self.api_base,
                "model": self.model,
            }
        except Exception as e:
            return {
                "status": "unavailable",
                "api_base": self.api_base,
                "model": self.model,
                "error": str(e),
            }
