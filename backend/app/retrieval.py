"""Source-preserving BM25 + SentenceTransformers/FAISS reciprocal-rank retrieval."""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from .neural import MODEL_CACHE, ROOT

EMBEDDING_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
INDEX_VERSION = 1
_ENCODER = None
_ENCODER_LOCK = threading.RLock()


def tokenize(text: str) -> list[str]:
    # Negations are retained. Normalization does not change source evidence.
    return re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.casefold())


def source_chunks(text: str, max_chars: int = 700, overlap: int = 120):
    """Cover all non-whitespace source text without changing a character."""
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            boundary = text.rfind(" ", start + max_chars // 2, end)
            if boundary > start:
                end = boundary
        if text[start:end].strip():
            yield start, end, text[start:end]
        if end == len(text):
            break
        start = max(start + 1, end - overlap)


def _load_encoder():
    global _ENCODER
    with _ENCODER_LOCK:
        if _ENCODER is None:
            import torch
            from sentence_transformers import SentenceTransformer

            torch.set_num_threads(max(1, int(os.getenv("TRIALOPS_TORCH_THREADS", "4"))))
            _ENCODER = SentenceTransformer(
                EMBEDDING_MODEL_ID, revision=EMBEDDING_REVISION, device="cpu",
                cache_folder=str(MODEL_CACHE), trust_remote_code=False,
                local_files_only=os.getenv("HF_HUB_OFFLINE", "0") == "1",
                model_kwargs={"use_safetensors": True})
        return _ENCODER


def _encode_complete(encoder, texts: list[str]) -> np.ndarray:
    """Avoid model's default silent 256-wordpiece truncation, even on unusual text.

    Typical source chunks need one embedding. Oversize chunks use 220-token
    windows whose embeddings are averaged and normalized. Exact source is kept.
    """
    windows, owners = [], []
    for i, text in enumerate(texts):
        offsets = encoder.tokenizer(text, add_special_tokens=False, return_offsets_mapping=True,
                                    truncation=False)["offset_mapping"]
        if len(offsets) <= 220:
            windows.append(text)
            owners.append(i)
        else:
            for start in range(0, len(offsets), 188):
                subset = offsets[start:start + 220]
                windows.append(text[subset[0][0]:subset[-1][1]])
                owners.append(i)
                if start + 220 >= len(offsets):
                    break
    with _ENCODER_LOCK:
        vectors = encoder.encode(windows, batch_size=32, normalize_embeddings=True,
                                 convert_to_numpy=True, show_progress_bar=False)
    result = np.zeros((len(texts), vectors.shape[1]), dtype=np.float32)
    counts = np.zeros((len(texts), 1), dtype=np.float32)
    for owner, vector in zip(owners, vectors):
        result[owner] += vector
        counts[owner] += 1
    result /= np.maximum(counts, 1)
    result /= np.maximum(np.linalg.norm(result, axis=1, keepdims=True), 1e-12)
    return np.ascontiguousarray(result, dtype=np.float32)


class RetrievalIndex:
    def __init__(self, studies: list[dict], index_dir: str | Path | None = None,
                 semantic: bool = True, allow_fallback: bool = True):
        self.index_dir = Path(index_dir) if index_dir is not None else ROOT / "data" / "index"
        self.semantic_enabled = semantic
        self.allow_fallback = allow_fallback
        self._lock = threading.RLock()
        self._faiss = None
        self._vectors = None
        self._encoder = None
        self._semantic_error = None
        self.chunks = []
        for study in studies:
            for field in ("title", "description", "eligibility_text"):
                text = study.get(field) or ""
                for i, (start, end, chunk) in enumerate(source_chunks(text)):
                    self.chunks.append({
                        "study_id": study["study_id"], "chunk_id": f"{study['study_id']}:{field}:{i}",
                        "source_url": study.get("source_url", ""), "source_field": field,
                        "start": start, "end": end, "text": chunk, "title": study.get("title", ""),
                        "countries": study.get("countries") or [], "status": study.get("status") or "UNKNOWN",
                        "conditions": study.get("conditions") or [],
                    })
        self._tokens = [tokenize(chunk["text"]) or ["__empty__"] for chunk in self.chunks]
        self._bm25 = BM25Okapi(self._tokens) if self._tokens else None
        self.corpus_sha256 = hashlib.sha256(json.dumps(self.chunks, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        self.last_search = {"status": "not_run"}

    @property
    def status(self) -> dict:
        return {"chunks": len(self.chunks), "lexical": "ready" if self._bm25 else "empty",
                "semantic": "ready" if self._faiss is not None else ("unavailable" if self._semantic_error else "not_loaded"),
                "semantic_error": self._semantic_error, "model_id": EMBEDDING_MODEL_ID,
                "version": EMBEDDING_REVISION, "corpus_sha256": self.corpus_sha256}

    def _load_persisted_vectors(self):
        manifest_path = self.index_dir / "manifest.json"
        vectors_path = self.index_dir / "embeddings.npy"
        if not manifest_path.exists() or not vectors_path.exists():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (manifest.get("version") != INDEX_VERSION or manifest.get("corpus_sha256") != self.corpus_sha256
                    or manifest.get("model_revision") != EMBEDDING_REVISION):
                return None
            if vectors_path.stat().st_size > 200_000_000:
                return None
            if hashlib.sha256(vectors_path.read_bytes()).hexdigest() != manifest.get("embeddings_sha256"):
                return None
            vectors = np.load(vectors_path, allow_pickle=False)
            if vectors.shape != (len(self.chunks), 384) or vectors.dtype != np.float32 or not np.isfinite(vectors).all():
                return None
            return np.ascontiguousarray(vectors)
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def build(self, persist: bool = True) -> dict:
        with self._lock:
            if self._faiss is not None or not self.chunks:
                return self.status
            if not self.semantic_enabled:
                self._semantic_error = "Semantic retrieval disabled by configuration."
                return self.status
            if self._semantic_error:
                return self.status
            try:
                import faiss

                self._encoder = _load_encoder()
                self._vectors = self._load_persisted_vectors()
                if self._vectors is None:
                    self._vectors = _encode_complete(self._encoder, [chunk["text"] for chunk in self.chunks])
                self._faiss = faiss.IndexFlatIP(self._vectors.shape[1])
                self._faiss.add(self._vectors)
                if persist:
                    self.save()
            except Exception as exc:
                self._faiss = None
                self._semantic_error = f"{type(exc).__name__}: semantic model/index unavailable; BM25 fallback only."
            return self.status

    def save(self):
        if self._faiss is None:
            raise RuntimeError("Build semantic index before saving")
        import faiss

        self.index_dir.mkdir(parents=True, exist_ok=True)
        vectors_path = self.index_dir / "embeddings.npy"
        np.save(vectors_path, self._vectors, allow_pickle=False)
        # Export for interoperability. Runtime safely rebuilds FAISS from validated NPY,
        # and deliberately never deserializes a supplied native FAISS binary.
        faiss.write_index(self._faiss, str(self.index_dir / "vectors.faiss"))
        (self.index_dir / "chunks.json").write_text(json.dumps(self.chunks, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest = {"version": INDEX_VERSION, "corpus_sha256": self.corpus_sha256,
                    "model_id": EMBEDDING_MODEL_ID, "model_revision": EMBEDDING_REVISION,
                    "embeddings_sha256": hashlib.sha256(vectors_path.read_bytes()).hexdigest(),
                    "chunks": len(self.chunks), "dimensions": int(self._vectors.shape[1]),
                    "metric": "cosine via normalized inner product", "chunking": "700 characters, 120 overlap; token-aware embedding windows"}
        (self.index_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def search_with_metadata(self, *args, **kwargs):
        """Keep per-request provenance together under concurrent API calls."""
        with self._lock:
            hits = self.search(*args, **kwargs)
            return hits, dict(self.last_search)

    def search(self, query: str, k: int = 5, mode: str = "hybrid", country: str | None = None,
               status: str | None = None) -> list[dict]:
        if mode not in {"bm25", "semantic", "hybrid"}:
            raise ValueError("mode must be bm25, semantic, or hybrid")
        if not isinstance(query, str) or len(query) > 4096:
            raise ValueError("query must be text of at most 4096 characters")
        if not 1 <= k <= 100:
            raise ValueError("k must be between 1 and 100")
        started = time.perf_counter()
        self.last_search = {"requested_mode": mode, "actual_mode": mode, "status": "ok"}
        terms = tokenize(query)
        if not terms or not self.chunks:
            self.last_search["status"] = "no_evidence"
            return []
        canonical_country = {"us": "united states", "usa": "united states"}.get((country or "").casefold(), (country or "").casefold())
        allowed = [i for i, chunk in enumerate(self.chunks)
                   if (not country or canonical_country in [value.casefold() for value in chunk["countries"]])
                   and (not status or chunk["status"].casefold().replace(" ", "_") == status.casefold().replace(" ", "_"))]
        if not allowed:
            self.last_search["status"] = "no_evidence"
            return []
        actual_mode = mode
        if mode != "bm25":
            self.build()
            if self._faiss is None:
                if not self.allow_fallback:
                    raise RuntimeError(self._semantic_error or "Semantic index unavailable")
                actual_mode = "bm25_fallback"
                self.last_search.update(status="degraded", actual_mode=actual_mode, reason=self._semantic_error)
        lexical_scores = self._bm25.get_scores(terms)
        # With tiny corpora, BM25 IDF can be <=0 even for present words. Presence
        # determines evidence inclusion; numerical scores only determine ordering.
        term_set = set(terms)
        lexical_order = sorted([i for i in allowed if term_set.intersection(self._tokens[i])],
                               key=lambda i: (-float(lexical_scores[i]), self.chunks[i]["chunk_id"]))
        semantic_order, semantic_scores = [], {}
        if actual_mode in {"semantic", "hybrid"}:
            try:
                vector = _encode_complete(self._encoder, [query])
                values, indices = self._faiss.search(vector, len(self.chunks))
                allowed_set = set(allowed)
                for score, i in zip(values[0], indices[0]):
                    if int(i) in allowed_set:
                        semantic_order.append(int(i))
                        semantic_scores[int(i)] = float(score)
            except Exception as exc:
                if not self.allow_fallback:
                    raise RuntimeError("Semantic query encoding failed") from exc
                actual_mode = "bm25_fallback"
                self.last_search.update(status="degraded", actual_mode=actual_mode,
                                        reason=f"{type(exc).__name__}: semantic query failed; BM25 used.")
        if actual_mode == "hybrid":
            scores = {}
            for ranking in (lexical_order, semantic_order):
                for rank, i in enumerate(ranking, 1):
                    scores[i] = scores.get(i, 0.0) + 1.0 / (60 + rank)
            order = sorted(scores, key=lambda i: (-scores[i], self.chunks[i]["chunk_id"]))
        elif actual_mode == "semantic":
            scores, order = semantic_scores, semantic_order
        else:
            scores, order = {i: float(lexical_scores[i]) for i in lexical_order}, lexical_order
        result = [{**self.chunks[i], "score": round(scores[i], 7), "actual_mode": actual_mode,
                   "bm25_score": round(float(lexical_scores[i]), 7),
                   "semantic_score": round(semantic_scores[i], 7) if i in semantic_scores else None,
                   "fallback_reason": self.last_search.get("reason")} for i in order[:k]]
        self.last_search.update(latency_ms=round((time.perf_counter() - started) * 1000, 3), result_count=len(result))
        return result
