"""Retrieval ablation against disclosed, exhaustive keyword-mention reference labels.

These qrels measure retrieval of mentions, NOT independent human judgments,
clinical interpretation, rule executability, or open-ended answer quality.
"""
from __future__ import annotations

import csv
import json
import math
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.retrieval import RetrievalIndex

QUERIES = [
    ("hba1c", "Which trials mention HbA1c or glycated hemoglobin criteria?", r"\bhba1c\b|glycated|glycosylated"),
    ("bmi", "Which trials mention body mass index BMI in eligibility?", r"body mass index|\bbmi\b"),
    ("metformin", "Find eligibility criteria mentioning metformin treatment.", r"\bmetformin\b"),
    ("insulin", "Find eligibility criteria mentioning insulin use.", r"\binsulin\b"),
    ("renal", "Which trials mention renal or kidney conditions in eligibility?", r"\brenal\b|\bkidney\b"),
    ("pregnancy", "Find pregnancy related eligibility language.", r"pregnan"),
    ("hypertension", "Find trial eligibility that mentions hypertension.", r"\bhypertension\b"),
    ("blood_pressure", "Which trials mention blood pressure criteria?", r"blood pressure"),
    ("malignancy", "Find criteria that mention cancer or malignancy.", r"\bcancer\b|malignan"),
    ("smoking", "Find smoking or tobacco related eligibility requirements.", r"smok|tobacco"),
    ("fasting", "Find trial criteria mentioning fasting measurements.", r"\bfasting\b"),
    ("cardiovascular", "Which eligibility texts mention cardiovascular conditions?", r"cardiovascular"),
]


def ranking_metrics(ranked_study_ids: list[str], relevant_ids: set[str], k: int = 5) -> dict:
    unique = list(dict.fromkeys(ranked_study_ids))[:k]
    relevance = [int(sid in relevant_ids) for sid in unique]
    hits = sum(relevance)
    dcg = sum(value / math.log2(rank + 2) for rank, value in enumerate(relevance))
    ideal = sum(1 / math.log2(rank + 2) for rank in range(min(k, len(relevant_ids))))
    return {"precision_at_5": hits / k, "recall_at_5": hits / len(relevant_ids) if relevant_ids else None,
            "reciprocal_rank_at_5": next((1 / (i + 1) for i, value in enumerate(relevance) if value), 0.0),
            "ndcg_at_5": dcg / ideal if ideal else None, "relevant_at_5": hits,
            "returned_study_ids": unique, "relevant_study_count": len(relevant_ids)}


def main():
    studies_path = ROOT / "data/processed/studies.json"
    studies = json.loads(studies_path.read_text(encoding="utf-8"))
    qrels = []
    for query_id, query, pattern in QUERIES:
        evidence = []
        for study in studies:
            text = study.get("eligibility_text") or ""
            match = re.search(pattern, text, re.I)
            if match:
                evidence.append({"study_id": study["study_id"], "source_url": study["source_url"],
                                 "source_field": "eligibility_text", "start": match.start(), "end": match.end(),
                                 "text": match.group()})
        qrels.append({"query_id": query_id, "query": query, "reference_regex": pattern,
                      "relevant_study_ids": [item["study_id"] for item in evidence], "source_evidence": evidence,
                      "label_provenance": "Developer-specified regex, exhaustively applied to original eligibility text; not independent human review"})
    index = RetrievalIndex(studies, allow_fallback=False)
    index.build()
    if index.status["semantic"] != "ready":
        raise RuntimeError(index.status["semantic_error"])
    rows = []
    for mode in ("bm25", "semantic", "hybrid"):
        for reference in qrels:
            started = time.perf_counter()
            # Retrieve 100 chunks then collapse by study. This benchmark is study
            # ranking; the UI's top source chunks are a different presentation.
            hits = index.search(reference["query"], k=100, mode=mode)
            latency = (time.perf_counter() - started) * 1000
            assert index.last_search["actual_mode"] == mode
            metric = ranking_metrics([h["study_id"] for h in hits], set(reference["relevant_study_ids"]))
            rows.append({"mode": mode, "query_id": reference["query_id"], "query": reference["query"],
                         **metric, "latency_ms": latency, "actual_mode": index.last_search["actual_mode"]})
    summary = {}
    for mode in ("bm25", "semantic", "hybrid"):
        subset = [row for row in rows if row["mode"] == mode]
        summary[mode] = {field: sum(row[field] for row in subset) / len(subset)
                         for field in ("precision_at_5", "recall_at_5", "reciprocal_rank_at_5", "ndcg_at_5", "latency_ms")}
    result = {"run_at_utc": datetime.now(timezone.utc).isoformat(), "query_count": len(qrels), "study_count": len(studies),
              "reference_type": "Heuristic exhaustive keyword-mention qrels, not human judgments",
              "index": index.status, "metrics": summary,
              "method": "Macro mean over 12 predeclared concept-mention queries; top 100 chunks collapsed into first five distinct studies. Precision denominator is always five.",
              "limitations": ["Lexical reference labels favor lexical retrieval; this is a mention-retrieval ablation, not a general semantic relevance benchmark.",
                              "A mention can be negated, contextual, inclusion or exclusion; labels do not assert eligibility semantics.",
                              "No relevance judgments were generated by an LLM or by the retrieval models.",
                              "The query set was designed after seeing the data domain; no hyperparameters were tuned on these outcomes.",
                              "Confidence intervals are omitted because 12 deliberately chosen concepts are not an independent representative sample."],
              "per_query": rows}
    output = ROOT / "reports/experiments"
    output.mkdir(parents=True, exist_ok=True)
    (output / "retrieval_qrels.json").write_text(json.dumps(qrels, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "reports/retrieval_benchmark.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    with (output / "retrieval_per_query.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axis = plt.subplots(figsize=(8.5, 4.8))
    names = list(summary)
    for i, metric in enumerate(("precision_at_5", "recall_at_5", "ndcg_at_5")):
        axis.bar([x + (i - 1) * 0.25 for x in range(len(names))], [summary[mode][metric] for mode in names], width=0.25,
                 label=metric.replace("_at_", "@").replace("_", " "))
    axis.set_xticks(range(len(names)), ["BM25", "Semantic", "Hybrid RRF"])
    axis.set_ylim(0, 1)
    axis.set_title("Retrieval ablation · 12 heuristic mention queries")
    axis.set_ylabel("Macro score; lexical qrels favor lexical retrieval")
    axis.legend()
    figure.tight_layout()
    figure.savefig(output / "retrieval_ablation.png", dpi=160)
    plt.close(figure)
    print(json.dumps({"report": str(ROOT / "reports/retrieval_benchmark.json"), "metrics": summary}, indent=2))


if __name__ == "__main__":
    main()
