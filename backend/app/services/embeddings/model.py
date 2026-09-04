"""
Local embedding model wrapper for product embeddings.

Model: BAAI/bge-small-en-v1.5 (384 dimensions), loaded locally via
sentence-transformers. No hosted API, no API key.

The model is loaded lazily and cached so scripts and services can call
`get_embedding_model()` without paying the load cost until embeddings
are actually needed.
"""

from functools import lru_cache

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSION = 384


class ProductEmbeddingModel:
    """
    Thin wrapper around a local sentence-transformers model.

    `encode` is kept minimal so tests can mock/fake it easily.
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME):
        self.model_name = model_name
        self._model = None

    def _ensure_loaded(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts, returning one 384-dim vector per text."""
        model = self._ensure_loaded()
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]


@lru_cache(maxsize=1)
def get_embedding_model() -> ProductEmbeddingModel:
    return ProductEmbeddingModel()
