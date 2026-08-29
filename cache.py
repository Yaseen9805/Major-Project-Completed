"""Persistent semantic cache backed by Qdrant (Module 2).

Replaces the prototype's in-memory list: entries survive process restarts,
similarity search stays cosine-based, and each entry expires 24h after its
*own* creation time (not a scheduled wipe of the whole cache) -- see
purge_expired() and cache_reaper.py.
"""

import time
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    PointStruct,
    Range,
    VectorParams,
)
from sentence_transformers import SentenceTransformer

from config import (
    CACHE_SIMILARITY_THRESHOLD,
    CACHE_TTL_SECONDS,
    EMBEDDING_MODEL_NAME,
    QDRANT_CACHE_COLLECTION,
    QDRANT_URL,
)

_model = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def embed(text: str):
    return _get_model().encode(text, normalize_embeddings=True).tolist()


class SemanticCache:
    """Qdrant-backed cache: one collection per instance.

    The module-level default instance below always uses the fixed
    QDRANT_CACHE_COLLECTION name so it persists across restarts. Tests (or
    anything else that wants an isolated cache) can pass their own
    collection_name.
    """

    def __init__(
        self,
        threshold: float = CACHE_SIMILARITY_THRESHOLD,
        collection_name: str = QDRANT_CACHE_COLLECTION,
        ttl_seconds: float = CACHE_TTL_SECONDS,
        client: QdrantClient | None = None,
    ):
        self.threshold = threshold
        self.collection_name = collection_name
        self.ttl_seconds = ttl_seconds
        self.client = client or QdrantClient(url=QDRANT_URL)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        if not self.client.collection_exists(self.collection_name):
            vector_size = _get_model().get_sentence_embedding_dimension()
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    def _freshness_filter(self) -> Filter:
        cutoff = time.time() - self.ttl_seconds
        return Filter(must=[FieldCondition(key="created_at", range=Range(gte=cutoff))])

    def check(self, query: str) -> dict | None:
        hits = self.client.search(
            collection_name=self.collection_name,
            query_vector=embed(query),
            query_filter=self._freshness_filter(),
            score_threshold=self.threshold,
            limit=1,
        )
        if not hits:
            return None

        match = hits[0]
        return {
            "answer": match.payload["answer"],
            "tier_used": match.payload["tier_used"],
            "matched_query": match.payload["query_text"],
            "similarity": match.score,
        }

    def add(self, query: str, answer: str, tier_used: str) -> None:
        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=embed(query),
            payload={
                "query_text": query,
                "answer": answer,
                "tier_used": tier_used,
                "created_at": time.time(),
            },
        )
        self.client.upsert(collection_name=self.collection_name, points=[point])

    def purge_expired(self) -> int:
        """Delete entries past their individual 24h TTL. Returns count before purge."""
        before = len(self)
        cutoff = time.time() - self.ttl_seconds
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=FilterSelector(
                filter=Filter(must=[FieldCondition(key="created_at", range=Range(lt=cutoff))])
            ),
        )
        return before - len(self)

    def clear(self) -> None:
        self.client.delete_collection(self.collection_name)
        self._ensure_collection()

    def __len__(self) -> int:
        return self.client.count(self.collection_name, exact=True).count


# Module-level default cache instance + functional API, matching the plan's
# `check_cache` / `add_to_cache` naming.
_default_cache = SemanticCache()


def check_cache(query: str, threshold: float = CACHE_SIMILARITY_THRESHOLD) -> dict | None:
    _default_cache.threshold = threshold
    return _default_cache.check(query)


def add_to_cache(query: str, answer: str, tier_used: str) -> None:
    _default_cache.add(query, answer, tier_used)


def clear_cache() -> None:
    _default_cache.clear()


def purge_expired_cache_entries() -> int:
    return _default_cache.purge_expired()
