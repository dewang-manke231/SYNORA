import hashlib
import json
import logging
import math
import re
from functools import lru_cache
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import httpx

from app.core.config import settings

logger = logging.getLogger("synora.embeddings")

DEFAULT_MOCK_DIMENSION = 64
DEFAULT_GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"


@lru_cache(maxsize=1)
def get_gemini_http_client() -> httpx.Client:
    """Reuse a bounded HTTP connection pool for Google AI calls."""
    return httpx.Client(
        timeout=httpx.Timeout(14.0, connect=4.0),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=30.0),
    )


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Computes cosine similarity between two float vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0

    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    sim = dot / (norm_a * norm_b)
    # Clamp to [-1.0, 1.0] to prevent floating point inaccuracies
    return max(-1.0, min(1.0, sim))


class EmbeddingProvider(ABC):
    """Abstract interface for generating vector embeddings."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimensionality."""
        pass

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Generates a normalized float vector for a given text."""
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generates embeddings for a batch of texts."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the provider is currently available."""
        pass

    @abstractmethod
    def get_provider_info(self) -> Dict[str, Any]:
        """Metadata about the active embedding provider."""
        pass


class DeterministicMockEmbeddingProvider(EmbeddingProvider):
    """
    Deterministic semantic vectorizer for local development, offline usage, and CI tests.
    Uses topic hub projections and term hashing to produce dense unit vectors
    where semantically and syntactically related texts naturally exhibit high
    cosine similarity (>= 0.70) while unrelated texts exhibit low cosine
    similarity (< 0.40).
    """

    def __init__(self, dimension: int = DEFAULT_MOCK_DIMENSION):
        self._dim = dimension
        self._stop_words = {
            "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of",
            "with", "is", "was", "are", "were", "be", "this", "that", "it",
            "what", "how", "do", "we", "can", "should", "from", "by", "as"
        }
        self._topic_map = {
            "consensus": ["raft", "consensus", "heartbeat", "election", "quorum", "leader", "timeout"],
            "failover": ["failover", "partition", "cluster", "region", "recovery", "split", "nodes", "network"],
            "streaming": ["kafka", "cdc", "stream", "offset", "pipeline", "mysql", "snowflake", "bigquery"],
            "security": ["vault", "tokens", "token", "auth", "oauth", "credentials", "rbac", "secret"],
            "architecture": ["architecture", "spec", "design", "database", "ledger", "transaction", "settlement"],
        }

    @property
    def dimension(self) -> int:
        return self._dim

    def is_available(self) -> bool:
        return True

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "provider": "mock",
            "model": f"deterministic-dense-hub-{self._dim}d",
            "dimension": self._dim,
            "is_mock": True,
            "status": "ready",
        }

    def _tokenize(self, text: str) -> List[str]:
        if not text:
            return []
        cleaned = re.sub(r"[^\w\s-]", " ", text.lower())
        words = [w.strip() for w in cleaned.split() if len(w.strip()) > 1]
        return [w for w in words if w not in self._stop_words]

    def embed_text(self, text: str) -> List[float]:
        # Background cone bias (models dense embedding space geometry)
        vec = [0.08] * self._dim
        tokens = self._tokenize(text)
        if not tokens:
            val = 1.0 / math.sqrt(self._dim)
            return [round(val, 6)] * self._dim

        # 1. Topic hub activations
        for topic_idx, (topic, topic_words) in enumerate(self._topic_map.items()):
            match_count = sum(1 for t in tokens if any(tw in t for tw in topic_words))
            if match_count > 0:
                start_dim = (topic_idx * 12) % self._dim
                for d in range(start_dim, start_dim + 12):
                    vec[d % self._dim] += 2.2 * math.log(1 + match_count)

        # 2. Term-level hashing for fine-grained specificity
        for t in tokens:
            h = int(hashlib.sha256(t.encode("utf-8")).hexdigest(), 16)
            for i in range(3):
                idx = (h >> (i * 8)) % self._dim
                vec[idx] += 0.75

        # Normalize to unit length
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [round(x / norm, 6) for x in vec]
        else:
            val = 1.0 / math.sqrt(self._dim)
            vec = [round(val, 6)] * self._dim
        return vec

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]


class GeminiEmbeddingProvider(EmbeddingProvider):
    """
    Google Gemini text-embedding client via REST API (e.g. text-embedding-004).
    Falls back gracefully to DeterministicMockEmbeddingProvider on network/auth error.
    """

    def __init__(self, api_key: str, model: str = DEFAULT_GEMINI_EMBEDDING_MODEL):
        self.api_key = api_key
        self.model = model
        self.mock_fallback = DeterministicMockEmbeddingProvider(dimension=DEFAULT_MOCK_DIMENSION)

    @property
    def dimension(self) -> int:
        return 3072

    def is_available(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("your_"))

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "provider": "gemini",
            "model": self.model,
            "dimension": self.dimension,
            "is_mock": False,
            "status": "configured" if self.is_available() else "unconfigured",
        }

    def embed_text(self, text: str) -> List[float]:
        if not self.is_available():
            return self.mock_fallback.embed_text(text)

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:embedContent?key={self.api_key}"
        payload = {
            "model": f"models/{self.model}",
            "content": {
                "parts": [{"text": text[:2048]}]
            }
        }

        try:
            res = get_gemini_http_client().post(endpoint, json=payload, timeout=httpx.Timeout(7.0, connect=3.0))
            if res.status_code == 200:
                data = res.json()
                values = data.get("embedding", {}).get("values", [])
                if values:
                    # Normalize vector
                    norm = math.sqrt(sum(x * x for x in values))
                    if norm > 0:
                        return [round(x / norm, 6) for x in values]
                    return values
            logger.warning(f"Gemini embedding call returned HTTP {res.status_code}: {res.text}. Falling back to mock embedder.")
            return self.mock_fallback.embed_text(text)
        except Exception as e:
            logger.error(f"Gemini embedding request failed: {e}. Falling back to mock embedder.")
            return self.mock_fallback.embed_text(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        # Generate individually or via batch
        return [self.embed_text(t) for t in texts]


def get_embedding_provider() -> EmbeddingProvider:
    """Returns the active embedding provider based on environment configuration."""
    provider_type = getattr(settings, "EMBEDDING_PROVIDER", "local").lower()
    gemini_key = getattr(settings, "GEMINI_API_KEY", None)

    if provider_type == "mock" or provider_type == "local":
        return DeterministicMockEmbeddingProvider()

    if provider_type == "gemini":
        if gemini_key and not gemini_key.startswith("your_"):
            return GeminiEmbeddingProvider(api_key=gemini_key)
        else:
            return DeterministicMockEmbeddingProvider()

    return DeterministicMockEmbeddingProvider()


def check_embedding_connectivity() -> Dict[str, Any]:
    """Inspects Gemini embedding API configuration and live connectivity status."""
    gemini_key = getattr(settings, "GEMINI_API_KEY", None)
    model = DEFAULT_GEMINI_EMBEDDING_MODEL

    if not gemini_key or gemini_key.startswith("your_"):
        return {
            "configured": False,
            "provider": "gemini",
            "model": model,
            "dimension": DEFAULT_MOCK_DIMENSION,
            "status": "missing_or_placeholder_key",
            "message": "GEMINI_API_KEY is not set or uses default placeholder. System operates safely with deterministic local vector embeddings.",
        }

    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}?key={gemini_key}"
    try:
        with httpx.Client(timeout=6.0) as client:
            resp = client.get(endpoint)
            if resp.status_code == 200:
                return {
                    "configured": True,
                    "provider": "gemini",
                    "model": model,
                    "dimension": 3072,
                    "status": "connected",
                    "message": f"Successfully connected to Gemini Embedding API ({model}).",
                }
            else:
                return {
                    "configured": False,
                    "provider": "gemini",
                    "model": model,
                    "dimension": DEFAULT_MOCK_DIMENSION,
                    "status": f"api_error_{resp.status_code}",
                    "message": f"Gemini Embedding API returned HTTP {resp.status_code}: {resp.text[:120]}",
                }
    except Exception as e:
        return {
            "configured": False,
            "provider": "gemini",
            "model": model,
            "dimension": DEFAULT_MOCK_DIMENSION,
            "status": "network_failure",
            "message": f"Could not reach Google Gemini Embedding endpoint: {str(e)}",
        }
