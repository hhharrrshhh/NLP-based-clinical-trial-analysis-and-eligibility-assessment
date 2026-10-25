"""Small local generation experiment, strictly separate from verified source quotes."""
from __future__ import annotations
import os
import re
import threading
import time
from .neural import MODEL_CACHE

MODEL_ID = "google/flan-t5-small"
REVISION = "0fc9ddf78a1e988dac52e2dac162b0ede4fd74ab"


class LocalGenerator:
    def __init__(self, local_files_only=None):
        self.local_files_only = os.getenv("HF_HUB_OFFLINE", "0") == "1" if local_files_only is None else local_files_only
        self.tokenizer = None
        self.model = None
        self.lock = threading.RLock()
        self.error = None

    def load(self):
        with self.lock:
            if self.model is not None:
                return self
            if self.error:
                raise RuntimeError(self.error)
            try:
                import torch
                from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
                torch.set_num_threads(max(1, int(os.getenv("TRIALOPS_TORCH_THREADS", "4"))))
                options = dict(revision=REVISION, cache_dir=str(MODEL_CACHE), trust_remote_code=False,
                               local_files_only=self.local_files_only)
                self.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, use_fast=True, **options)
                self.model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_ID, use_safetensors=True, **options).to("cpu").eval()
            except Exception as error:
                self.error = f"{type(error).__name__}: local generation unavailable; check public weights and dependencies."
                raise RuntimeError(self.error) from error
        return self

    def generate(self, question, evidence):
        started = time.perf_counter()
        base = {"model": MODEL_ID, "revision": REVISION, "backend": "local", "device": "cpu", "verified": False,
                "reason": "Experimental generated draft. Exact source citations are supplied separately; they do not verify generated claims. Human review required."}
        if not evidence:
            return {**base, "status": "no_evidence", "text": None}
        try:
            self.load()
        except RuntimeError as error:
            return {**base, "status": "unavailable", "text": None, "reason": str(error)}
        import torch
        # An instruction-tuned 77M model has limited context and reasoning. Explicitly
        # record selected excerpts and truncation instead of hiding context loss.
        question_used = question[:300]
        prefix = "Source excerpt:\n"
        suffix = f"\n\nQuestion: {question_used}\nAnswer:"
        with self.lock, torch.inference_mode():
            prefix_size = len(self.tokenizer.encode(prefix + suffix, add_special_tokens=False))
            budget = max(1, 480 - prefix_size)
            hit = evidence[0]
            text = str(hit["text"])
            offsets = self.tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)["offset_mapping"]
            end = offsets[min(len(offsets), budget) - 1][1] if offsets else 0
            excerpt = text[:end]
            prompt = prefix + excerpt + suffix
            inputs = self.tokenizer(prompt, return_tensors="pt", truncation=False)
            if inputs["input_ids"].shape[1] > 512:
                return {**base, "status": "context_limit", "text": None, "reason": "Input exceeds this model's 512-token experiment limit."}
            output = self.model.generate(**inputs, do_sample=False, num_beams=1, max_new_tokens=96)
            generated = self.tokenizer.decode(output[0], skip_special_tokens=True).strip()
        numbers = set(re.findall(r"\d+(?:\.\d+)?", generated))
        source_numbers = set(re.findall(r"\d+(?:\.\d+)?", excerpt))
        # This narrow guard flags invented numbers; it does not prove entailment.
        unsupported_numbers = sorted(numbers - source_numbers)
        return {**base, "status": "generated_draft", "text": generated,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "input_tokens": int(inputs["input_ids"].shape[1]), "max_new_tokens": 96,
                "prompt_format": "Source excerpt followed by question and answer cue; prompt development is not a held-out quality evaluation",
                "question_truncated": question_used != question, "evidence_truncated": len(excerpt) < len(text) or len(evidence) > 1,
                "source_context": [{"study_id": hit["study_id"], "source_url": hit.get("source_url"), "text": excerpt,
                                    "source_field": hit.get("source_field"), "start": hit.get("start"),
                                    "end": hit.get("start", 0) + len(excerpt)}],
                "guard": {"unsupported_numeric_tokens": unsupported_numbers, "entailment_verified": False}}


generator = LocalGenerator()
