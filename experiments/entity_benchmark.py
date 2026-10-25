"""Exploratory held-out CHIA entity comparison with real published annotations.

The corpus labels are independent of both model predictions. No fine-tuning occurs.
The dictionary sees only training-study annotations. Test selection is by study ID.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psutil
from backend.app.neural import BiomedicalNER

SCOPE = {"Condition", "Drug", "Procedure"}
MODEL_MAP = {"Disease_disorder": "Condition", "Medication": "Drug",
             "Diagnostic_procedure": "Procedure", "Therapeutic_procedure": "Procedure"}


def annotations(path: Path, text: str):
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("T"):
            continue
        pieces = line.split("\t")
        if len(pieces) < 3:
            continue
        category, _, bounds = pieces[1].partition(" ")
        if category not in SCOPE:
            continue
        spans = tuple(tuple(map(int, span.split())) for span in bounds.split(";"))
        if any(start < 0 or end > len(text) or end <= start for start, end in spans):
            raise ValueError(f"Invalid annotation offsets in {path.name}")
        extracted = " ".join(text[start:end] for start, end in spans)
        if extracted != pieces[2]:
            raise ValueError(f"Text/annotation mismatch in {path.name}: {pieces[0]}")
        result.append((category, spans, extracted))
    return result


def stats(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
            "false_negative_rate": fn / (tp + fn) if tp + fn else None,
            "false_positive_rate": None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-studies", type=int, default=20)
    args = parser.parse_args()
    source = ROOT / "data/external/chia"
    files = sorted(source.glob("NCT*_*.txt"))
    if not files:
        raise FileNotFoundError("CHIA not downloaded; see ingestion documentation")
    by_study = defaultdict(list)
    for path in files:
        by_study[path.name.split("_")[0]].append(path)
    study_order = sorted(by_study, key=lambda sid: hashlib.sha256(("trialops-chia-v1:" + sid).encode()).hexdigest())
    split_at = int(len(study_order) * 0.8)
    training_ids = set(study_order[:split_at])
    heldout_ids = study_order[split_at:]
    test_ids = set(heldout_ids[:args.test_studies])
    assert training_ids.isdisjoint(test_ids)
    counts = defaultdict(Counter)
    training_annotations = 0
    excluded_documents = []
    for sid in sorted(training_ids):
        for path in by_study[sid]:
            # BRAT offsets address original bytes decoded as UTF-8, including CRLF.
            text = path.read_bytes().decode("utf-8")
            try:
                labeled = annotations(path.with_suffix(".ann"), text)
            except ValueError as exc:
                excluded_documents.append({"document_id": path.stem, "split": "train", "reason": str(exc)})
                continue
            for category, spans, mention in labeled:
                training_annotations += 1
                if len(spans) == 1 and len(mention.strip()) >= 3:
                    counts[mention.casefold()][category] += 1
    dictionary = {term: sorted(labels, key=lambda label: (-labels[label], label))[0] for term, labels in counts.items()}
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(t) for t in sorted(dictionary, key=lambda s: (-len(s), s))) + r")(?!\w)", re.IGNORECASE)
    test_docs = []
    for sid in sorted(test_ids):
        for path in by_study[sid]:
            text = path.read_bytes().decode("utf-8")
            try:
                gold = annotations(path.with_suffix(".ann"), text)
            except ValueError as exc:
                excluded_documents.append({"document_id": path.stem, "split": "test", "reason": str(exc)})
                continue
            test_docs.append({"study_id": sid, "document_id": path.stem, "text": text, "gold": gold,
                              "text_sha256": hashlib.sha256(text.encode()).hexdigest()})
    output = ROOT / "reports/experiments"
    output.mkdir(parents=True, exist_ok=True)
    model = BiomedicalNER()
    load_ms = None
    totals, per_document, all_predictions = {}, [], []
    for name in ("training_dictionary", "biomedical_transformer"):
        tp = fp = fn = empty = 0
        latencies = []
        rss = [psutil.Process().memory_info().rss]
        stop = threading.Event()

        def sample():
            process = psutil.Process()
            while not stop.wait(0.02):
                rss.append(process.memory_info().rss)

        thread = threading.Thread(target=sample, daemon=True)
        thread.start()
        if name == "biomedical_transformer":
            load_started = time.perf_counter()
            model.load()
            load_ms = (time.perf_counter() - load_started) * 1000
        per_category = {category: [0, 0, 0] for category in sorted(SCOPE)}
        for document in test_docs:
            started = time.perf_counter()
            if name == "training_dictionary":
                predicted = {(dictionary[match.group().casefold()], ((match.start(), match.end()),))
                             for match in pattern.finditer(document["text"])}
            else:
                result = model.predict(document["text"])
                if result["status"] != "ok":
                    raise RuntimeError(result.get("error", result["status"]))
                predicted = {(MODEL_MAP[e["label"]], ((e["start"], e["end"]),))
                             for e in result["entities"] if e["label"] in MODEL_MAP}
            latency = (time.perf_counter() - started) * 1000
            latencies.append(latency)
            gold = {(category, spans) for category, spans, _ in document["gold"]}
            true_positive, false_positive, false_negative = len(gold & predicted), len(predicted - gold), len(gold - predicted)
            tp += true_positive
            fp += false_positive
            fn += false_negative
            empty += not predicted
            for category in SCOPE:
                g = {e for e in gold if e[0] == category}
                p = {e for e in predicted if e[0] == category}
                per_category[category] = [a + b for a, b in zip(per_category[category], (len(g & p), len(p - g), len(g - p)))]
            per_document.append({"model": name, "study_id": document["study_id"],
                                 "document_id": document["document_id"], **stats(true_positive, false_positive, false_negative),
                                 "gold_count": len(gold), "prediction_count": len(predicted), "latency_ms": latency})
            all_predictions.append({"model": name, "study_id": document["study_id"], "document_id": document["document_id"],
                                    "gold": sorted(gold), "predictions": sorted(predicted), "text_sha256": document["text_sha256"]})
        stop.set()
        thread.join()
        rss.append(psutil.Process().memory_info().rss)
        totals[name] = {**stats(tp, fp, fn), "document_count": len(test_docs),
                        "empty_prediction_document_rate": empty / len(test_docs),
                        "mean_inference_latency_ms": sum(latencies) / len(latencies),
                        "rss_start_mib": rss[0] / 2**20, "sampled_peak_process_rss_mib": max(rss) / 2**20,
                        "per_category": {category: stats(*values) for category, values in per_category.items()}}
    report = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(), "experiment": "Exploratory cross-corpus entity transfer, not full eligibility extraction",
        "dataset": "CHIA v2 with_scope", "license": "CC BY 4.0",
        "source_file": "chia_with_scope.zip", "source_download_url": "https://ndownloader.figshare.com/files/21728850",
        "citation": "Kury et al. (2020), Chia Annotated Datasets, https://doi.org/10.6084/m9.figshare.11855817.v2",
        "label_provenance": "Published CHIA human annotations; no model-generated ground truth",
        "scope": sorted(SCOPE), "biomedical_label_mapping": MODEL_MAP,
        "evaluation": "Exact category and exact full span tuple; discontinuous gold spans count and cannot match contiguous model spans",
        "annotation_validation": {"method": "Original CRLF preserved; every selected span checked against BRAT mention text. Entire documents with invalid source spans excluded, rather than guessing corrected offsets.",
                                  "excluded_documents": excluded_documents, "excluded_document_count": len(excluded_documents)},
        "split": {"method": "Study IDs sorted by sha256('trialops-chia-v1:' + study_id); first 80% train; first requested studies of remaining 20% test",
                  "available_studies": len(study_order), "train_studies": len(training_ids), "heldout_studies": len(heldout_ids),
                  "test_studies": sorted(test_ids), "training_study_ids": sorted(training_ids),
                  "training_annotations": training_annotations, "dictionary_terms": len(dictionary),
                  "test_documents": len(test_docs), "leakage_check": "train/test study intersection empty"},
        "transformer": {"model_id": result["model_id"], "revision": result["version"], "load_ms": load_ms,
                        "fine_tuning": "not performed", "device": "cpu"},
        "metrics": totals,
        "limitations": ["Coarse ontology mapping is imperfect; CHIA Condition and MACCROBAT Disease_disorder are not equivalent.",
                        "This is a fixed exploratory subset of the held-out partition, not an official CHIA test benchmark.",
                        "Shared upstream pretraining exposure cannot be ruled out; only project-level train/test separation is verified.",
                        "False-positive rate requires a defined true-negative universe; span extraction has none, so it is null. Precision and FP counts are reported.",
                        "Empty prediction rate is a coverage proxy, not calibrated abstention or rule uncertainty.",
                        "Sampled RSS includes imported libraries; it is not exclusive per-model memory. Transformer peak includes load.",
                        "No eligibility-rule accuracy or regional causality can be inferred from entity F1."]}
    (output / "entity_benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (ROOT / "reports/entity_benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output / "entity_predictions.jsonl").write_text("\n".join(json.dumps(row) for row in all_predictions) + "\n", encoding="utf-8")
    with (output / "entity_per_document.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(per_document[0]))
        writer.writeheader()
        writer.writerows(per_document)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axis = plt.subplots(figsize=(8, 4.5))
    names = list(totals)
    for i, metric in enumerate(("precision", "recall", "f1")):
        axis.bar([x + (i - 1) * 0.25 for x in range(len(names))], [totals[name][metric] for name in names], width=0.25, label=metric.capitalize())
    axis.set_xticks(range(len(names)), ["Training dictionary", "Biomedical transformer"])
    axis.set_ylim(0, 1)
    axis.set_ylabel("Exact-span micro score")
    axis.set_title(f"CHIA exploratory entity transfer · {len(test_docs)} held-out documents")
    axis.legend()
    figure.tight_layout()
    figure.savefig(output / "entity_comparison.png", dpi=160)
    plt.close(figure)
    print(json.dumps({"report": str(output / "entity_benchmark.json"), "metrics": totals}, indent=2))


if __name__ == "__main__":
    main()
