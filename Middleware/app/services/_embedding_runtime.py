"""
Singleton-обёртка над sentence-transformers для всех векторных индексов middleware.

Модель `paraphrase-multilingual-MiniLM-L12-v2` загружается один раз и
переиспользуется в `metadata_service`, `drone_index_service` и
`component_index_service`. Если sentence-transformers не установлен или
загрузка модели падает, все индексы переходят в режим word-overlap fallback.
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

_USE_ML: Optional[bool] = None
_model = None


def _try_load_model():
    """Lazy-инициализация singleton-модели. Возвращает (model, USE_ML)."""
    global _USE_ML, _model
    if _USE_ML is not None:
        return _model, _USE_ML

    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401
    except ImportError:
        _USE_ML = False
        _model = None
        return _model, _USE_ML

    try:
        from sentence_transformers import SentenceTransformer
        print(f"Loading embedding model ({MODEL_NAME})...")
        _model = SentenceTransformer(MODEL_NAME)
        _USE_ML = True
        print("Embedding model loaded.")
    except Exception as exc:  # pragma: no cover - окружение без модели
        print(f"Failed to load embedding model: {exc}")
        _model = None
        _USE_ML = False

    return _model, _USE_ML


def is_ml_available() -> bool:
    """True, если sentence-transformers установлен и модель загрузилась."""
    _, use_ml = _try_load_model()
    return use_ml


def encode_texts(texts: List[str]) -> Optional[np.ndarray]:
    """Векторизовать список текстов одной моделью.

    Возвращает np.ndarray формы (N, D) или None, если ML недоступен.
    Каллер отвечает за fallback на rule-based поиск при None.
    """
    if not texts:
        return None
    model, use_ml = _try_load_model()
    if not use_ml or model is None:
        return None
    try:
        return model.encode(texts, convert_to_numpy=True)
    except Exception as exc:  # pragma: no cover
        print(f"encode_texts failed: {exc}")
        return None


def encode_query(text: str) -> Optional[np.ndarray]:
    """Векторизовать одиночный запрос. Возвращает np.ndarray (D,) или None."""
    if not text:
        return None
    arr = encode_texts([text])
    if arr is None:
        return None
    return arr[0]


def cosine_sim_matrix(query_emb: np.ndarray, corpus_emb: np.ndarray) -> np.ndarray:
    """Косинусное сходство query_emb (D,) со всеми векторами corpus_emb (N, D)."""
    query_norm = query_emb / (np.linalg.norm(query_emb) or 1.0)
    corpus_norms = np.linalg.norm(corpus_emb, axis=1, keepdims=True)
    corpus_norms[corpus_norms == 0] = 1.0
    corpus_normalized = corpus_emb / corpus_norms
    return corpus_normalized @ query_norm


def reset_model_for_tests() -> None:
    """Сбросить singleton — для unit-тестов с monkeypatch."""
    global _USE_ML, _model
    _USE_ML = None
    _model = None


__all__ = [
    "MODEL_NAME",
    "is_ml_available",
    "encode_texts",
    "encode_query",
    "cosine_sim_matrix",
    "reset_model_for_tests",
]
