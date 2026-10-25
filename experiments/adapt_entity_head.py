"""Train a small CHIA BIO head on frozen biomedical DistilBERT representations.

This is a real supervised head-adaptation experiment, not full transformer
fine-tuning and not India/US domain adaptation. The original CHIA test studies
remain untouched until model selection on disjoint development studies finishes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import random
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import psutil
import torch
from torch import nn
from backend.app.neural import BiomedicalNER, NER_MODEL_ID, NER_REVISION
from experiments.entity_benchmark import SCOPE, annotations, stats

LABELS = ["O", "B-Condition", "I-Condition", "B-Drug", "I-Drug", "B-Procedure", "I-Procedure"]
LABEL_IDS = {label: i for i, label in enumerate(LABELS)}
SOURCE_ARCHIVE_SHA256 = "b51ec05ba42a3805daf9581dd22a305986f7c5ae3ca4dad36b70d37970fb69b2"


def encode_document(ner, text):
    """Frozen features for every token, resolving duplicate windows by centrality."""
    encoded = ner._tokenizer(text, return_offsets_mapping=True, return_overflowing_tokens=True,
                             max_length=512, stride=64, truncation=True, padding=True, return_tensors="pt")
    offsets = encoded.pop("offset_mapping").tolist()
    encoded.pop("overflow_to_sample_mapping", None)
    selected = {}
    with torch.inference_mode():
        for batch_start in range(0, len(offsets), 4):
            batch = {key: value[batch_start:batch_start + 4] for key, value in encoded.items()}
            hidden = ner._model.base_model(**batch).last_hidden_state
            for row in range(hidden.shape[0]):
                window = offsets[batch_start + row]
                positions = [i for i, (start, end) in enumerate(window) if end > start]
                if not positions:
                    continue
                first, last = positions[0], positions[-1]
                for position in positions:
                    key = tuple(window[position])
                    margin = min(position - first, last - position)
                    if key not in selected or margin > selected[key][0]:
                        selected[key] = (margin, hidden[row, position].clone())
    ordered = sorted(selected)
    if not ordered:
        return [], torch.empty((0, ner._model.config.dim))
    return ordered, torch.stack([selected[key][1] for key in ordered]).clone()


def align_labels(offsets, gold):
    """Ignore ambiguous/discontinuous or boundary-straddling supervision.

    Offsets refer to the original UTF-8-decoded text, preserving CRLF. BIO labels
    cover every wordpiece, with B on the first piece at the entity start. A token
    crossing an annotated boundary cannot represent that boundary and is ignored.
    """
    labels = []
    ignored = 0
    for start, end in offsets:
        candidates = [(category, spans) for category, spans, _ in gold
                      if any(a < end and b > start for a, b in spans)]
        if not candidates:
            labels.append(0)
        elif len(candidates) != 1 or len(candidates[0][1]) != 1:
            labels.append(-100)
            ignored += 1
        else:
            category, spans = candidates[0]
            a, b = spans[0]
            if start < a or end > b:
                labels.append(-100)
                ignored += 1
                continue
            prefix = "B" if start == a else "I"
            labels.append(LABEL_IDS[f"{prefix}-{category}"])
    return torch.tensor(labels, dtype=torch.long), ignored


def decode(offsets, label_ids, text):
    result, current = set(), None
    for (start, end), label_id in zip(offsets, label_ids):
        label = LABELS[label_id]
        prefix, _, category = label.partition("-")
        continuation = current is not None and prefix == "I" and category == current[0] and not text[current[2]:start].strip()
        if not continuation and current is not None:
            result.add((current[0], ((current[1], current[2]),)))
            current = None
        if label == "O":
            continue
        if continuation:
            current = (category, current[1], end)
        else:
            current = (category, start, end)
    if current:
        result.add((current[0], ((current[1], current[2]),)))
    return result


def evaluate(head, docs):
    head.eval()
    tp = fp = fn = 0
    rows = []
    per_category = {category: [0, 0, 0] for category in sorted(SCOPE)}
    with torch.inference_mode():
        for doc in docs:
            started = time.perf_counter()
            prediction = decode(doc["offsets"], head(doc["features"]).argmax(-1).tolist(), doc["text"])
            head_ms = (time.perf_counter() - started) * 1000
            gold = {(category, spans) for category, spans, _ in doc["gold"]}
            dtp, dfp, dfn = len(gold & prediction), len(prediction - gold), len(gold - prediction)
            tp += dtp
            fp += dfp
            fn += dfn
            for category in SCOPE:
                g = {entity for entity in gold if entity[0] == category}
                p = {entity for entity in prediction if entity[0] == category}
                per_category[category] = [a + b for a, b in zip(per_category[category],
                                                               (len(g & p), len(p - g), len(g - p)))]
            rows.append({"study_id": doc["study_id"], "document_id": doc["document_id"],
                         **stats(dtp, dfp, dfn), "prediction_count": len(prediction), "gold_count": len(gold),
                         "encoder_ms": doc["encoder_ms"], "head_ms": head_ms,
                         "predictions": sorted(prediction), "gold": sorted(gold),
                         "text_sha256": hashlib.sha256(doc["text"].encode()).hexdigest()})
    return {**stats(tp, fp, fn), "per_category": {key: stats(*value) for key, value in per_category.items()}}, rows


def render_report_figures(report):
    """Render measured saved results without fitting or selecting another model."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    history = report["history"]
    best_epoch = report["head"]["selected_epoch"]
    figure, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].plot([row["epoch"] for row in history], [row["training_loss"] for row in history], marker="o")
    axes[0].set_ylabel("Weighted cross-entropy training loss")
    axes[1].plot([row["epoch"] for row in history], [row["dev"]["f1"] for row in history], marker="o")
    axes[1].axvline(best_epoch, color="#e16a47", linestyle="--", label=f"Selected epoch {best_epoch}")
    axes[1].set_ylabel("Development exact-span micro F1")
    axes[1].set_ylim(0, 1)
    axes[1].legend()
    for axis in axes:
        axis.set_xlabel("Training epoch")
    figure.suptitle("CHIA frozen-encoder head adaptation")
    figure.tight_layout()
    figure.savefig(ROOT / "reports/adaptation_learning_curve.png", dpi=160)
    plt.close(figure)

    comparison = report["comparison_with_original_benchmark"]["metrics"]
    names = ["training_dictionary", "biomedical_transformer", "adapted_frozen_encoder_head"]
    figure, axis = plt.subplots(figsize=(9, 4.5))
    for i, metric in enumerate(("precision", "recall", "f1")):
        axis.bar([x + (i - 1) * 0.25 for x in range(len(names))],
                 [comparison[name][metric] for name in names], width=0.25, label=metric.capitalize())
    axis.set_xticks(range(len(names)), ["Dictionary\n800 train studies", "Original biomedical\ntransformer", "Frozen encoder + BIO head\n100 train studies"])
    axis.set_ylim(0, 1)
    axis.set_ylabel("Exact-span micro score")
    axis.set_title("Same CHIA held-out test: 20 studies, 40 documents, 328 gold spans")
    axis.legend()
    figure.tight_layout()
    figure.savefig(ROOT / "reports/adaptation_comparison.png", dpi=160)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-studies", type=int, default=100)
    parser.add_argument("--dev-studies", type=int, default=20)
    parser.add_argument("--epochs", type=int, default=8)
    args = parser.parse_args()
    if args.train_studies < 1 or args.dev_studies < 1 or args.epochs < 1:
        raise ValueError("Counts must be positive")
    random.seed(17)
    np.random.seed(17)
    torch.manual_seed(17)
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True)
    source = ROOT / "data/external/chia"
    by_study = defaultdict(list)
    for path in sorted(source.glob("NCT*_*.txt")):
        by_study[path.name.split("_")[0]].append(path)
    if not by_study:
        raise FileNotFoundError("No CHIA source documents; see docs/adaptation.md")
    study_order = sorted(by_study, key=lambda sid: hashlib.sha256(("trialops-chia-v1:" + sid).encode()).hexdigest())
    split_at = int(len(study_order) * 0.8)
    if args.train_studies + args.dev_studies > split_at:
        raise ValueError("Requested train/dev studies must fit original training partition")
    split_ids = {"train": study_order[:args.train_studies],
                 "dev": study_order[args.train_studies:args.train_studies + args.dev_studies],
                 "test": study_order[split_at:split_at + 20]}
    assert not (set(split_ids["train"]) & set(split_ids["dev"]) or set(split_ids["train"]) & set(split_ids["test"])
                or set(split_ids["dev"]) & set(split_ids["test"]))
    baseline_path = ROOT / "reports/entity_benchmark.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    if set(split_ids["test"]) != set(baseline["split"]["test_studies"]):
        raise ValueError("Adaptation test studies do not match the original entity benchmark")
    model = BiomedicalNER(local_files_only=True)
    rss = [psutil.Process().memory_info().rss]
    stop = threading.Event()

    def sample():
        process = psutil.Process()
        while not stop.wait(0.05):
            rss.append(process.memory_info().rss)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    overall = time.perf_counter()
    load_started = time.perf_counter()
    model.load()
    load_ms = (time.perf_counter() - load_started) * 1000
    for parameter in model._model.parameters():
        parameter.requires_grad_(False)
    documents = {split: [] for split in split_ids}
    excluded = []
    ignored = {split: 0 for split in split_ids}
    def load_documents(split):
        ids = split_ids[split]
        for sid in ids:
            for path in by_study[sid]:
                text = path.read_bytes().decode("utf-8")
                try:
                    gold = annotations(path.with_suffix(".ann"), text)
                except ValueError as exc:
                    excluded.append({"document_id": path.stem, "split": split, "reason": str(exc)})
                    continue
                started = time.perf_counter()
                offsets, features = encode_document(model, text)
                encoder_ms = (time.perf_counter() - started) * 1000
                labels, count = align_labels(offsets, gold)
                ignored[split] += count
                documents[split].append({"study_id": sid, "document_id": path.stem, "text": text,
                                         "gold": gold, "offsets": offsets, "features": features,
                                         "labels": labels, "encoder_ms": encoder_ms})
            if len(documents[split]) % 20 == 0:
                print(f"Encoding {split}: {len(documents[split])} documents", flush=True)
        if not documents[split]:
            raise ValueError(f"No valid documents in {split}")
        print(f"Encoded {split}: {len(documents[split])} documents", flush=True)
    # Only train/dev documents are read before model selection. The held-out
    # source annotations and encoder features are opened after selecting an epoch.
    for split in ("train", "dev"):
        load_documents(split)
    features = torch.cat([doc["features"] for doc in documents["train"]])
    targets = torch.cat([doc["labels"] for doc in documents["train"]])
    valid = targets != -100
    features, targets = features[valid], targets[valid]
    # Normalization statistics are learned only from training features.
    mean = features.mean(0)
    scale = features.std(0).clamp(min=0.01)
    for docs in (documents["train"], documents["dev"]):
        for doc in docs:
            doc["features"] = (doc["features"] - mean) / scale
    features = (features - mean) / scale
    class_counts = torch.bincount(targets, minlength=len(LABELS))
    class_weights = (class_counts.sum() / (len(LABELS) * class_counts.clamp(min=1))).sqrt().clamp(max=10)
    head = nn.Linear(features.shape[1], len(LABELS))
    optimizer = torch.optim.AdamW(head.parameters(), lr=0.001, weight_decay=0.0001)
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    history, best_state, best_f1, best_epoch = [], None, -1, None
    training_started = time.perf_counter()
    for epoch in range(1, args.epochs + 1):
        head.train()
        permutation = torch.randperm(len(targets))
        total_loss = 0.0
        for offset in range(0, len(targets), 512):
            indices = permutation[offset:offset + 512]
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(head(features[indices]), targets[indices])
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach()) * len(indices)
        dev_metrics, _ = evaluate(head, documents["dev"])
        history.append({"epoch": epoch, "training_loss": total_loss / len(targets), "dev": dev_metrics})
        if dev_metrics["f1"] > best_f1:
            best_f1, best_epoch = dev_metrics["f1"], epoch
            best_state = {name: value.detach().clone() for name, value in head.state_dict().items()}
        print(f"Epoch {epoch}: dev exact span F1 {dev_metrics['f1']:.4f}", flush=True)
    training_seconds = time.perf_counter() - training_started
    head.load_state_dict(best_state)
    selected_dev_metrics, _ = evaluate(head, documents["dev"])
    baseline_predictions_path = ROOT / "reports/experiments/entity_predictions.jsonl"
    baseline_documents = {row["document_id"]: row for line in baseline_predictions_path.read_text(encoding="utf-8").splitlines()
                          if (row := json.loads(line))["model"] == "biomedical_transformer"}
    load_documents("test")
    for doc in documents["test"]:
        doc["features"] = (doc["features"] - mean) / scale
        prior = baseline_documents.get(doc["document_id"])
        gold = sorted((category, spans) for category, spans, _ in doc["gold"])
        if (prior is None or prior["text_sha256"] != hashlib.sha256(doc["text"].encode()).hexdigest()
                or json.loads(json.dumps(gold)) != prior["gold"]):
            raise ValueError(f"Original benchmark text/gold mismatch: {doc['document_id']}")
    if {doc["document_id"] for doc in documents["test"]} != set(baseline_documents):
        raise ValueError("Adaptation test documents do not match original benchmark documents")
    test_metrics, test_rows = evaluate(head, documents["test"])
    test_metrics["mean_encoder_plus_head_latency_ms"] = sum(row["encoder_ms"] + row["head_ms"] for row in test_rows) / len(test_rows)
    artifact_dir = ROOT / "models/adapted_chia_head"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    from safetensors.torch import save_file
    save_file({**{f"head.{key}": value for key, value in best_state.items()}, "feature_mean": mean,
               "feature_scale": scale}, str(artifact_dir / "head.safetensors"))
    stop.set()
    sampler.join()
    rss.append(psutil.Process().memory_info().rss)
    comparison = {name: {key: value for key, value in metrics.items() if key in
                        ("tp", "fp", "fn", "precision", "recall", "f1", "false_negative_rate", "false_positive_rate")}
                  for name, metrics in baseline["metrics"].items()}
    comparison["adapted_frozen_encoder_head"] = {key: value for key, value in test_metrics.items()
                                                 if key != "per_category"}
    report = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(), "status": "completed", "experiment": "Frozen biomedical encoder with supervised CHIA BIO linear head",
        "dataset": "CHIA v2 with_scope", "source_download_url": "https://ndownloader.figshare.com/files/21728850", "license": "CC BY 4.0",
        "citation": "Kury et al. (2020), Chia Annotated Datasets, https://doi.org/10.6084/m9.figshare.11855817.v2",
        "source_archive_sha256": SOURCE_ARCHIVE_SHA256,
        "label_provenance": "Published CHIA human Condition/Drug/Procedure annotations, validated against original CRLF-preserved text",
        "encoder": {"model_id": NER_MODEL_ID, "revision": NER_REVISION, "frozen": True},
        "head": {"architecture": f"Linear({features.shape[1]}, {len(LABELS)})", "trainable_parameters": sum(p.numel() for p in head.parameters()),
                 "labels": LABELS, "optimizer": "AdamW", "learning_rate": 0.001, "weight_decay": 0.0001, "batch_size": 512,
                 "epochs": args.epochs, "selected_epoch": best_epoch, "selection": "Highest development exact-span micro F1; earlier epoch on tie",
                 "class_weights": class_weights.tolist(), "class_token_counts": class_counts.tolist(), "seed": 17,
                 "artifact": "models/adapted_chia_head/head.safetensors", "artifact_sha256": hashlib.sha256((artifact_dir / "head.safetensors").read_bytes()).hexdigest()},
        "split": {"method": f"Same SHA256 by-study partition as entity_benchmark; first {args.train_studies} original-training studies train, next {args.dev_studies} dev, first 20 original-heldout studies test",
                  "study_ids": split_ids, "document_counts": {key: len(value) for key, value in documents.items()},
                  "document_ids": {key: [doc["document_id"] for doc in value] for key, value in documents.items()},
                  "train_tokens": len(targets), "ignored_ambiguous_discontinuous_or_boundary_tokens": ignored,
                  "supervision": {key: {"gold_spans": sum(len(doc["gold"]) for doc in value),
                                        "discontinuous_gold_spans": sum(len(spans) != 1 for doc in value for _, spans, _ in doc["gold"]),
                                        "tokens": sum(len(doc["offsets"]) for doc in value)} for key, value in documents.items()},
                  "excluded_invalid_documents": excluded, "study_overlap": 0},
        "label_alignment": "Offsets on original UTF-8-decoded text with CRLF retained. All wordpieces inside a unique contiguous annotation receive B at the annotated start and I thereafter. Tokens intersecting overlapping/discontinuous annotations or crossing annotation boundaries use loss ignore_index=-100; other tokens receive O. Exact evaluation includes all mapped gold spans, including unrepresentable discontinuous spans.",
        "history": history, "selected_dev": selected_dev_metrics, "test": test_metrics, "per_document": test_rows,
        "comparison_with_original_benchmark": {"baseline_report": "reports/entity_benchmark.json",
                "baseline_report_sha256": hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
                "same_test_studies_documents_text_hashes_and_gold": True, "metrics": comparison,
                "f1_delta_vs_biomedical_transformer": test_metrics["f1"] - baseline["metrics"]["biomedical_transformer"]["f1"],
                "f1_delta_vs_training_dictionary": test_metrics["f1"] - baseline["metrics"]["training_dictionary"]["f1"]},
        "performance": {"training_seconds_excluding_frozen_encoding": training_seconds,
                        "encoder_load_ms": load_ms,
                        "total_seconds_including_load_encoding_training_evaluation": time.perf_counter() - overall,
                        "sampled_peak_process_rss_mib": max(rss) / 2**20, "rss_sample_interval_ms": 50,
                        "device": "cpu", "threads": 4, "python": platform.python_version(), "torch": torch.__version__,
                        "platform": platform.platform(), "processor": platform.processor(),
                        "physical_cpu_cores": psutil.cpu_count(logical=False), "logical_cpu_count": psutil.cpu_count(),
                        "ram_total_gib": psutil.virtual_memory().total / 2**30},
        "limitations": ["Only the 5,383-parameter linear head is trained; this is not end-to-end transformer fine-tuning.",
                        "CHIA adaptation is distinct from India/US adaptation, which lacks comparable independent regional labels.",
                        "Train100/dev20/test20 study selection is fixed before this run; test is evaluated only after development epoch selection.",
                        "Dictionary baseline used more training studies (800), so comparison does not isolate architecture under equal training data.",
                        "Overlapping/discontinuous and boundary-straddling supervision is ignored for training tokens; full mapped gold spans still count in exact test evaluation.",
                        "The experiment is exploratory with one seed; no clinical efficacy or calibrated reliability is established.",
                        "Feature encoding latency and head decoding are separately timed and summed; production request overhead is excluded.",
                        "The adapted model is an experimental evaluation artifact, not connected to eligibility-rule execution."]}
    output = ROOT / "reports/adaptation_benchmark.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (artifact_dir / "manifest.json").write_text(json.dumps({key: report[key] for key in ("encoder", "head", "split")}, indent=2), encoding="utf-8")
    with (ROOT / "reports/adaptation_per_document.csv").open("w", newline="", encoding="utf-8") as file:
        fields = [key for key in test_rows[0] if key not in ("predictions", "gold")]
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(test_rows)
    (ROOT / "reports/experiments").mkdir(parents=True, exist_ok=True)
    render_report_figures(report)
    print(json.dumps({"report": str(output), "test": test_metrics, "performance": report["performance"]}, indent=2))


if __name__ == "__main__":
    main()
