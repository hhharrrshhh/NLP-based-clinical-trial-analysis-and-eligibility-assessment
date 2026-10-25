"""Real, optional biomedical token classification; never an eligibility decision model."""
from __future__ import annotations

import math
import os
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NER_MODEL_ID = "d4data/biomedical-ner-all"
NER_REVISION = "015a4050c9ac99722e61c547aa9b4282bcbedc7f"
MODEL_CACHE = Path(os.getenv("TRIALOPS_MODEL_CACHE", str(ROOT / "models" / "hf")))


class BiomedicalNER:
    """Load pinned safetensors lazily, with CPU inference and full-text token windows.

    Overlapping windows vote by distance from their boundary, then BIO labels are
    aggregated. Offsets always address the exact original input, not cleaned text.
    Unavailable weights return explicit unavailable status, never regex predictions.
    """

    def __init__(self, local_files_only: bool | None = None):
        self.local_files_only = (os.getenv("HF_HUB_OFFLINE", "0") == "1") if local_files_only is None else local_files_only
        self._tokenizer = None
        self._model = None
        self._lock = threading.RLock()
        self._error = None

    def load(self):
        with self._lock:
            if self._model is not None:
                return self
            # Retry is explicit: a failed request does not repeatedly download weights.
            if self._error:
                raise RuntimeError(self._error)
            try:
                import torch
                from transformers import AutoModelForTokenClassification, AutoTokenizer

                torch.set_num_threads(max(1, int(os.getenv("TRIALOPS_TORCH_THREADS", "4"))))
                kwargs = dict(revision=NER_REVISION, cache_dir=str(MODEL_CACHE),
                              local_files_only=self.local_files_only, trust_remote_code=False)
                self._tokenizer = AutoTokenizer.from_pretrained(NER_MODEL_ID, use_fast=True, **kwargs)
                self._model = AutoModelForTokenClassification.from_pretrained(
                    NER_MODEL_ID, use_safetensors=True, **kwargs).to("cpu").eval()
            except Exception as exc:
                self._error = f"{type(exc).__name__}: biomedical model unavailable; check model cache/network and server logs."
                raise RuntimeError(self._error) from exc
        return self

    def predict(self, text: str) -> dict:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if len(text) > 100_000:
            raise ValueError("Text exceeds 100,000 characters; submit separate source sections.")
        started = time.perf_counter()
        base = {"model_id": NER_MODEL_ID, "version": NER_REVISION, "device": "cpu",
                "entities": [], "status": "not_run", "input_characters": len(text),
                "role": "Biomedical entity detection only; not an eligibility-rule parser."}
        if not text.strip():
            return {**base, "status": "empty_input", "latency_ms": 0.0, "windows": 0}
        try:
            self.load()
        except RuntimeError as exc:
            return {**base, "status": "unavailable", "error": str(exc),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3)}
        import torch

        with self._lock, torch.inference_mode():
            encoded = self._tokenizer(
                text, return_offsets_mapping=True, return_overflowing_tokens=True,
                max_length=512, stride=64, truncation=True, padding=True, return_tensors="pt")
            offsets = encoded.pop("offset_mapping").tolist()
            encoded.pop("overflow_to_sample_mapping", None)
            selected = {}
            for batch_start in range(0, len(offsets), 4):
                batch = {key: value[batch_start:batch_start + 4] for key, value in encoded.items()}
                probabilities = self._model(**batch).logits.softmax(dim=-1)
                scores, labels = probabilities.max(dim=-1)
                for row in range(scores.shape[0]):
                    window_offsets = offsets[batch_start + row]
                    content_positions = [i for i, (start, end) in enumerate(window_offsets) if end > start]
                    if not content_positions:
                        continue
                    first, last = content_positions[0], content_positions[-1]
                    for token_i in content_positions:
                        start, end = window_offsets[token_i]
                        margin = min(token_i - first, last - token_i)
                        key = (start, end)
                        candidate = (margin, self._model.config.id2label[int(labels[row, token_i])], float(scores[row, token_i]))
                        if key not in selected or margin > selected[key][0]:
                            selected[key] = candidate
            entities = []
            current = None
            for (start, end), (_, label, confidence) in sorted(selected.items()):
                prefix, _, category = label.partition("-")
                continuation = (current is not None and prefix == "I" and category == current["label"]
                                and not text[current["end"]:start].strip())
                if not continuation and current is not None:
                    current["text"] = text[current["start"]:current["end"]]
                    current["score"] = round(sum(current.pop("_scores")) / current.pop("_count"), 6)
                    entities.append(current)
                    current = None
                if prefix == "O" or not category:
                    continue
                if continuation:
                    current["end"] = end
                    current["_scores"].append(confidence)
                    current["_count"] += 1
                else:
                    current = {"start": start, "end": end, "label": category,
                               "_scores": [confidence], "_count": 1}
            if current is not None:
                current["text"] = text[current["start"]:current["end"]]
                current["score"] = round(sum(current.pop("_scores")) / current.pop("_count"), 6)
                entities.append(current)
        return {**base, "entities": entities, "status": "ok", "windows": len(offsets),
                "tokens_processed": len(selected), "truncated": False,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3)}
