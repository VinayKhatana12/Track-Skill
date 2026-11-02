"""Text embedding for the AI module — lazy, cached, with a laptop-safe fallback.

Model choices:
- Sentence-transformers mode (USE_LIGHT_NLP=false): ``all-MiniLM-L6-v2``.
  Chosen because it is small (~22M parameters), fast on CPU, and the de
  facto standard for short-text semantic similarity (skills, job titles,
  tracer replies). Embeddings are L2-normalized so cosine similarity is a
  plain dot product.
- Light mode (USE_LIGHT_NLP=true, the default): a deterministic hashed
  n-gram embedder (word unigrams + character trigrams, MD5-hashed into a
  fixed 512-dim space, L2-normalized). No model download, no numpy, no GPU —
  it runs anywhere and is fully deterministic, at the cost of lexical rather
  than semantic similarity. This is the documented fallback so the whole
  product runs on a laptop.

Both implementations satisfy the same interface: ``encode(texts) -> list[list[float]]``
returning L2-normalized dense vectors. The embedder is created lazily on
first use and cached for the process lifetime; tests can reset the cache.
"""

import hashlib
import math
from typing import Any

from app.core.config import get_settings

EMBEDDING_DIM = 512

_embedder: Any = None


class EmbeddingBackendError(RuntimeError):
    """Raised when the selected embedding backend cannot be initialised."""


class HashingEmbedder:
    """Deterministic hashed n-gram embedder (the light fallback).

    Word unigrams plus character trigrams give partial robustness to
    inflections and typos; MD5 hashing keeps the mapping stable across
    processes (Python's built-in hash() is randomly seeded).
    """

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * EMBEDDING_DIM
            tokens = _tokenize(text)
            if tokens:
                for token in tokens:
                    char_features = (
                        f"c:{token[start:start + 3]}"
                        for start in range(max(1, len(token) - 2))
                    )
                    for feature in ("w:" + token, *char_features):
                        index = _hash_index(feature)
                        vector[index] += 1.0
                norm = math.sqrt(sum(value * value for value in vector)) or 1.0
                vector = [round(value / norm, 6) for value in vector]
            vectors.append(vector)
        return vectors


class SentenceTransformerEmbedder:
    """all-MiniLM-L6-v2 sentence embeddings (optional heavy backend)."""

    def __init__(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - environment-dependent
            raise EmbeddingBackendError(
                "USE_LIGHT_NLP=false requires the sentence-transformers package. "
                "Install it with: pip install sentence-transformers"
            ) from exc
        self._model = SentenceTransformer("all-MiniLM-L6-v2")

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [[float(value) for value in vector] for vector in vectors]


def _tokenize(text: str) -> set[str]:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in text.lower())
    words = {word for word in cleaned.split() if len(word) > 1}
    return words


def _hash_index(feature: str) -> int:
    digest = hashlib.md5(feature.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % EMBEDDING_DIM


def get_embedder():
    """Return the process-wide embedder, creating it lazily on first use."""
    global _embedder
    if _embedder is None:
        if get_settings().use_light_nlp:
            _embedder = HashingEmbedder()
        else:
            _embedder = SentenceTransformerEmbedder()
    return _embedder


def reset_embedder() -> None:
    """Drop the cached embedder (used by tests when flipping USE_LIGHT_NLP)."""
    global _embedder
    _embedder = None


def cosine(left: list[float], right: list[float]) -> float:
    """Cosine similarity for L2-normalized vectors — a plain dot product."""
    if not left or not right:
        return 0.0
    small, large = (left, right) if len(left) <= len(right) else (right, left)
    return sum(a * b for a, b in zip(small, large, strict=True))
