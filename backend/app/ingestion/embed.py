from functools import lru_cache

import numpy as np

from app.config import get_settings


@lru_cache
def _get_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().embedding_model)


def embed_documents(texts: list[str]) -> list[np.ndarray]:
    """Embed chunk text for storage. multilingual-e5 models expect a
    'passage: ' prefix for documents and 'query: ' for queries."""
    if not texts:
        return []
    prefixed = [f"passage: {t}" for t in texts]
    vectors = _get_model().encode(prefixed, normalize_embeddings=True, show_progress_bar=False)
    return list(vectors)


def embed_query(text: str) -> np.ndarray:
    vectors = _get_model().encode([f"query: {text}"], normalize_embeddings=True, show_progress_bar=False)
    return vectors[0]
