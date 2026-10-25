# Experimental local generated drafts

`backend/app/generation.py` runs the public [google/flan-t5-small](https://huggingface.co/google/flan-t5-small) model on CPU. Its official card declares Apache-2.0 and 77 million parameters. The exact revision is `0fc9ddf78a1e988dac52e2dac162b0ede4fd74ab`; the cache is the same ignored `models/hf` directory used by the other models. It uses safetensors, a fast tokenizer, `trust_remote_code=False`, greedy decoding and at most 96 generated tokens. No credential is needed for these public weights.

Only an explicitly requested assistant draft invokes generation. The default `GENERATOR_BACKEND=local` selects this model. `none` disables generation. `ollama` selects the separately configured `OLLAMA_URL`/`OLLAMA_MODEL` adapter; adapter/outage handling is tested, but no actual Ollama inference is claimed. Set these process environment variables before running `scripts/start.ps1`; scripts do not automatically load `.env`.

The local generator receives only a bounded selected evidence excerpt and the question. The source chunk retains a study ID, source URL, source field and original offsets. Question/evidence selection and truncation are explicit in the output, with an input limit of 512 tokens and a smaller context budget. Unselected retrieved sources remain available in the main answer but are not implied to have been read by the generator. Local cached loading is supported by `HF_HUB_OFFLINE=1`.

Reproduce the inference test:

```powershell
.\.venv\Scripts\python.exe -m scripts.generation_smoke
```

The actual real-source smoke asked what HbA1c requirement was written in a retrieved NCT03760991 excerpt. The observed output was **“Glycated hemoglobin”**, which does not answer the range question adequately. This negative finding is preserved in `reports/generation_smoke.json`. The test's `passed` status means the model loaded and generated nonempty output; it does not score answer correctness. `reports/generation_prompt_probe.json` also records illustrative prompt-development observations on a clearly synthetic context. These observations are not an independent quality benchmark and were not used as ground truth for the entity or rule experiments.

Generated drafts always have `verified=false`. A numeric-token guard flags numbers absent from the selected source; an empty list of such numbers does not prove correctness. Exact source quote verification does not establish entailment of generated prose. The UI marks the draft as unverified and keeps the source text/citations available. The generator has no access to tool dispatch, profile observations, environment credentials, executable code, registry thresholds or review approval. It cannot authorize eligibility rules.

The small model's limited quality is a remaining scientific/product limitation. A stronger backend with an independent answer-quality and entailment benchmark would be needed for reliable generative explanations. The useful verified path remains deterministic analysis and retrieved source excerpts.
