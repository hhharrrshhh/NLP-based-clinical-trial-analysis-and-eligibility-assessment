# Stage 0: verified starting state

The active objective incorporates the supplied master prompt and subsequent execution clarifications. Work continues in the original repository; nothing has been recreated or discarded.

The original demo passes its four checks and reproduces the expected 60 synthetic evaluations. The first implementation session saved NLP, eligibility, neural and retrieval modules, but stopped at an account usage limit before their validation. They are retained and being tested. The Python 3.11 virtual environment installation completed successfully and `python -m pip check` reports no broken requirements. Actual installed torch/safetensors versions are reflected in requirements.

There were no previous Git commits. The initial safe checkpoint includes only explicitly selected source/configuration/reference files, not downloaded models/corpora or credentials. The guide text remains local. `.env`, virtual environments, model weights, database files, and external corpora are ignored. Public registry snapshots are retained with provenance when produced.

`pytest.ini` discovers only `tests/`. The legacy demo remains under `legacy/` with an independently reproducible command in `prototype_audit.md`. No frozen legacy agent/RAG tests existed at this audit. Any such tests added later belong under `legacy/tests/` and run explicitly with `python -m pytest legacy/tests`; they must not silently become clinical NLP gates, and must not be deleted to hide failures. Active retrieval/API tests remain part of the integrated application verification.

Hardware observed: AMD Ryzen 7 7435HS, 16 logical CPUs, 25,439,199,232 bytes RAM, NVIDIA RTX 3050 Laptop GPU with approximately 4 GB VRAM. CPU inference is the portable default. Docker client 29.7.2 is present but Linux engine named pipe is missing. No local LLM credential or expert annotations are assumed. CHIA's published annotations can support an exploratory benchmark, not expert validation of the newly retrieved regional study rules.

Audit outcome: implementation can proceed. Scientific validation, new module tests, inference, live API/UI, and Docker execution are not claimed as complete at Stage 0.
