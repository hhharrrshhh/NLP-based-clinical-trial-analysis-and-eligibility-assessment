"""Download pinned biomedical weights and record actual CPU inference measurements."""
from __future__ import annotations

import json
import platform
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psutil
from backend.app.neural import BiomedicalNER


def main():
    process = psutil.Process()
    memory = [process.memory_info().rss]
    stop = threading.Event()

    def sample():
        while not stop.wait(0.05):
            memory.append(process.memory_info().rss)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    model = BiomedicalNER()
    example = "Participants aged 18 to 65 years with type 2 diabetes must not have severe renal impairment."
    cold = model.predict(example)
    warm = model.predict(example)
    long_text = ("Participants have type 2 diabetes and use metformin. " * 160) + "Severe renal impairment is excluded."
    long_result = model.predict(long_text) if cold["status"] == "ok" else None
    real = None
    studies_path = ROOT / "data/processed/studies.json"
    if studies_path.exists() and cold["status"] == "ok":
        studies = json.loads(studies_path.read_text(encoding="utf-8"))
        study = next((s for s in studies if s.get("eligibility_text")), None)
        if study:
            real = {"study_id": study["study_id"], "source_url": study["source_url"],
                    "input": study["eligibility_text"], "output": model.predict(study["eligibility_text"])}
    stop.set()
    sampler.join()
    result = {"run_at_utc": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
              "platform": platform.platform(), "cpu_logical_count": psutil.cpu_count(),
              "ram_total_gib": round(psutil.virtual_memory().total / 2**30, 3),
              "device": "cpu", "torch_threads": 4, "input": example,
              "input_provenance": "synthetic demonstration, not a clinical protocol or patient record",
              "cold": cold, "warm": warm,
              "memory": {"rss_before_mib": round(memory[0] / 2**20, 3),
                         "rss_sampled_peak_mib": round(max(memory) / 2**20, 3),
                         "sampling_interval_ms": 50,
                         "meaning": "Process RSS during load and inference; not model-only or exact allocator peak."},
              "long_input": {"characters": len(long_text), "output": long_result}, "real_study": real}
    if long_result and long_result["status"] == "ok":
        result["long_input"]["tail_entity_detected"] = any(e["start"] > len(long_text) - 40 for e in long_result["entities"])
        assert long_result["windows"] > 1
        assert all(long_text[e["start"]:e["end"]] == e["text"] for e in long_result["entities"])
    path = ROOT / "reports/model_smoke.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(path), "status": cold["status"], "cold_ms": cold["latency_ms"],
                      "warm_ms": warm["latency_ms"], "memory": result["memory"]}, indent=2))
    return 0 if cold["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
