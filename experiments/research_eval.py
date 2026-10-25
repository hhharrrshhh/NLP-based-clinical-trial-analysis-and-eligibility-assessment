"""Reproducible developer-reference and descriptive registry evaluation.

Run: python -m experiments.research_eval
No parameter fitting, country threshold substitution, or label generation occurs
here. References are explicit files authored without calling extract().
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import itertools
import json
from pathlib import Path
import platform
import statistics
import sys
import time
import tracemalloc
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import psutil
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from backend.app.eligibility import evaluate_profile
from backend.app.nlp import extract, normalize_text, tokenize

ROOT = Path(__file__).resolve().parents[1]
DIMENSIONS = ("field", "operator", "value", "unit", "type", "negation", "logical_shape")


def ratio(numerator: int | float, denominator: int | float) -> dict:
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def semantic_signature(rule: dict) -> dict:
    """Remove evidence/IDs, preserve all semantic fields and the whole tree."""
    if rule.get("kind") == "group":
        return {"kind": "group", "logic": rule.get("logic"), "type": rule.get("type"),
                "children": [semantic_signature(child) for child in rule.get("children", [])]}
    result = {key: rule.get(key) for key in ("kind", "field", "operator", "unit", "type")}
    result["negated"] = bool(rule.get("negated", False))
    for key in ("value", "lower", "upper", "lower_inclusive", "upper_inclusive", "unit_assumed"):
        if key in rule:
            result[key] = rule[key]
    return result


def equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return bool(np.isclose(left, right, rtol=0, atol=1e-6))
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(equal(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(equal(a, b) for a, b in zip(left, right))
    return left == right


def projection(rule: dict, dimension: str) -> Any:
    if dimension == "logical_shape":
        return [rule.get("logic"), [projection(child, dimension) for child in rule.get("children", [])]] if rule["kind"] == "group" else "ATOM"
    if rule["kind"] == "group":
        # Preserve path alignment; no field is scored on a selected subset.
        own = rule.get("type") if dimension == "type" else rule.get("logic") == "NOT" if dimension == "negation" else None
        return [own, [projection(child, dimension) for child in rule["children"]]]
    if dimension == "value":
        return {key: rule[key] for key in ("value", "lower", "upper", "lower_inclusive", "upper_inclusive") if key in rule}
    if dimension == "unit":
        return [rule.get("unit"), rule.get("unit_assumed")]
    return rule.get("negated", False) if dimension == "negation" else rule.get(dimension)


def reference_summary(rows: list[dict]) -> dict:
    positives = [row for row in rows if row["expected_executable"]]
    negatives = [row for row in rows if not row["expected_executable"]]
    tp = sum(row["predicted_executable"] for row in positives)
    fp = sum(row["predicted_executable"] for row in negatives)
    tn, fn = len(negatives) - fp, len(positives) - tp
    return {"case_count": len(rows), "expected_executable_count": len(positives),
            "expected_unsupported_count": len(negatives),
            "confusion": {"positive_class": "complete executable semantic representation", "TP": tp, "FP": fp, "TN": tn, "FN": fn},
            "false_positive_rate": ratio(fp, len(negatives)), "false_negative_rate": ratio(fn, len(positives)),
            "binary_accuracy": ratio(tp + tn, len(rows)), "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn),
            "abstention_rate": ratio(sum(not row["predicted_executable"] for row in rows), len(rows)),
            "unsupported_abstention": ratio(tn, len(negatives)),
            "full_rule_match_expected_executable": ratio(sum(row["full_rule_match"] for row in positives), len(positives)),
            "full_signature_match_including_unsupported": ratio(sum(row["full_rule_match"] for row in rows), len(rows)),
            "component_case_exact_accuracy": {dimension: ratio(sum(row["components"][dimension] for row in positives), len(positives)) for dimension in DIMENSIONS},
            "partial_execution_on_unsupported_count": sum(row["emitted_rule_count"] > 0 for row in negatives),
            "span_integrity": ratio(sum(row["span_integrity"] for row in rows), len(rows))}


def evaluate_references(path: Path) -> tuple[dict, list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert len({case["case_id"] for case in cases}) == len(cases)
    family_splits: dict[str, set] = {}
    rows = []
    for case in cases:
        family_splits.setdefault(case["study_id"], set()).add(case["split"])
        output = extract(case["text"], case["study_id"])
        actual = [semantic_signature(rule) for rule in output["rules"]]
        expected = case["expected_rules"]
        # Any unsupported residue means no complete representation. Also report
        # emitted fragments separately so partial-execution errors cannot hide.
        executable = bool(actual) and not output["unresolved"] and not output["contradictions"]
        source_items = [*output["entities"], *output["rules"], *output["unresolved"]]
        spans_valid = all(item["source_text"] == case["text"][item["source_start"]:item["source_end"]] for item in source_items)
        rows.append({"case_id": case["case_id"], "study_id": case["study_id"], "family": case["family"], "split": case["split"],
                     "label_origin": case["label_origin"], "text": case["text"],
                     "expected_executable": case["expected_executable"], "predicted_executable": executable,
                     "expected_signature": expected, "predicted_signature": actual,
                     "emitted_rule_count": len(actual), "unresolved_count": len(output["unresolved"]),
                     "full_rule_match": equal(expected, actual), "span_integrity": spans_valid,
                     "components": {dimension: equal([projection(rule, dimension) for rule in expected], [projection(rule, dimension) for rule in actual]) for dimension in DIMENSIONS}})
    assert all(len(splits) == 1 for splits in family_splits.values()), "Synthetic source-family leakage"
    return {"label_origin": payload["label_origin"], "expert_reviewed": False, "blinded": False,
            "scope": payload["positive_definition"], "split_definition": payload["split_definition"],
            "metric_definition": "Component accuracies are whole-case exact matches over ALL expected-executable cases, including abstentions; missing/extra atoms and group paths are errors. Type means inclusion versus exclusion_constraint. Negation includes lexical negated flags and NOT scope. Full match preserves tree shape, bounds, unit assumptions, and canonical units; numeric tolerance 1e-6. This is engineering reference fidelity, not clinical extraction accuracy.",
            "training": "No model trained and no parser parameters changed using these references.",
            "all": reference_summary(rows),
            "by_split": {split: reference_summary([row for row in rows if row["split"] == split]) for split in ("train", "dev", "test")},
            "failures": [{key: row[key] for key in ("case_id", "split", "text", "expected_signature", "predicted_signature")} for row in rows if not row["full_rule_match"]]}, rows


def study_split(study_id: str) -> str:
    return "train" if int(hashlib.sha256(study_id.encode("utf-8")).hexdigest(), 16) % 10 < 8 else "test"


def region_of(study: dict) -> str:
    countries = set(study.get("countries", []))
    india, usa = "India" in countries, "United States" in countries
    return "shared" if india and usa else "India_only" if india else "US_only" if usa else "other"


def lexical_tokens(text: str) -> list[str]:
    # ALL stopwords are retained, including no/not/without/and/or. This is
    # tokenization and case normalization; it is not lemmatization or stemming.
    return [item["text"].casefold() for item in tokenize(normalize_text(text)) if any(char.isalnum() for char in item["text"])]


def jsd(left: Counter, right: Counter) -> float | None:
    if not left or not right:
        return None
    vocabulary = sorted(left.keys() | right.keys())
    p = np.array([left[word] for word in vocabulary], dtype=float)
    q = np.array([right[word] for word in vocabulary], dtype=float)
    p /= p.sum()
    q /= q.sum()
    middle = (p + q) / 2
    a, b = p > 0, q > 0
    return float((np.sum(p[a] * np.log2(p[a] / middle[a])) + np.sum(q[b] * np.log2(q[b] / middle[b]))) / 2)


def regional_evaluation(studies: list[dict]) -> tuple[dict, list[dict]]:
    ids = [study["study_id"] for study in studies]
    assert len(ids) == len(set(ids)), "Duplicate study IDs would leak across regions/splits"
    train_indices = [index for index, study in enumerate(studies) if study_split(study["study_id"]) == "train"]
    test_indices = [index for index, study in enumerate(studies) if study_split(study["study_id"]) == "test"]
    texts = [study.get("eligibility_text", "") for study in studies]
    vectorizer = TfidfVectorizer(tokenizer=lexical_tokens, token_pattern=None, lowercase=False, stop_words=None)
    vectorizer.fit([texts[index] for index in train_indices])
    matrix = vectorizer.transform(texts)
    vocabulary = set(vectorizer.vocabulary_)
    terms = vectorizer.get_feature_names_out()
    tokens = [lexical_tokens(text) for text in texts]
    rows = []
    for study, words in zip(studies, tokens):
        output = extract(study.get("eligibility_text", ""), study["study_id"])
        stats = output["stats"]
        rows.append({"study_id": study["study_id"], "region": region_of(study), "split": study_split(study["study_id"]),
                     "countries": "|".join(study.get("countries", [])), "source_url": study.get("source_url"),
                     "source_label_origin": "ClinicalTrials.gov unannotated registry text",
                     "criterion_count": stats["criterion_count"], "parsed_count": stats["parsed_count"],
                     "unresolved_count": stats["unresolved_count"], "entity_count": stats["entity_count"],
                     "criterion_coverage": stats["parsed_count"] / stats["criterion_count"] if stats["criterion_count"] else None,
                     "requires_human_validation": output["requires_human_validation"],
                     "token_count": len(words), "oov_token_count": sum(word not in vocabulary for word in words),
                     "oov_rate": sum(word not in vocabulary for word in words) / len(words) if words else None,
                     "sentence_count": len(output["preprocessing"]["sentences"]),
                     "latency_ms_single_descriptive_pass": stats["latency_ms"]})
    regions = ["India_only", "US_only", "shared"]
    groups = {}
    for region in regions:
        selected = [row for row in rows if row["region"] == region]
        criteria = sum(row["criterion_count"] for row in selected)
        parsed = sum(row["parsed_count"] for row in selected)
        indices = [index for index, study in enumerate(studies) if region_of(study) == region]
        mean_tfidf = np.asarray(matrix[indices].mean(axis=0)).ravel() if indices else np.zeros(len(terms))
        top = np.argsort(mean_tfidf)[::-1][:15]
        groups[region] = {"study_count": len(selected), "split_counts": dict(Counter(row["split"] for row in selected)),
                          "criteria": criteria, "parsed_rules": parsed,
                          "micro_criterion_coverage": ratio(parsed, criteria),
                          "mean_study_coverage": statistics.mean(row["criterion_coverage"] for row in selected if row["criterion_coverage"] is not None) if selected else None,
                          "studies_with_at_least_one_rule": sum(row["parsed_count"] > 0 for row in selected),
                          "studies_requiring_human_validation": sum(row["requires_human_validation"] for row in selected),
                          "token_oov_vs_train_vocabulary": ratio(sum(row["oov_token_count"] for row in selected), sum(row["token_count"] for row in selected)),
                          "top_mean_tfidf_terms": [{"term": str(terms[index]), "weight": float(mean_tfidf[index])} for index in top if mean_tfidf[index] > 0],
                          "extraction_accuracy": None, "accuracy_unavailable_reason": "No independently adjudicated regional rule labels exist."}
    comparisons = []
    for scope in ("all_descriptive", "test_only"):
        for left, right in itertools.combinations(regions, 2):
            li = [i for i, row in enumerate(rows) if row["region"] == left and (scope != "test_only" or row["split"] == "test")]
            ri = [i for i, row in enumerate(rows) if row["region"] == right and (scope != "test_only" or row["split"] == "test")]
            lc = Counter(word for index in li for word in tokens[index])
            rc = Counter(word for index in ri for word in tokens[index])
            cosine = float(cosine_similarity(np.asarray(matrix[li].mean(axis=0)), np.asarray(matrix[ri].mean(axis=0)))[0, 0]) if li and ri else None
            comparisons.append({"scope": scope, "left": left, "right": right,
                                "left_studies": len(li), "right_studies": len(ri),
                                "unigram_js_divergence_base2": jsd(lc, rc),
                                "vocabulary_jaccard": len(lc.keys() & rc.keys()) / len(lc.keys() | rc.keys()) if lc and rc else None,
                                "train_fitted_tfidf_centroid_cosine": cosine})
    fingerprints: dict[str, list[str]] = {}
    for study in studies:
        digest = hashlib.sha256(" ".join(lexical_tokens(study.get("eligibility_text", ""))).encode()).hexdigest()
        fingerprints.setdefault(digest, []).append(study["study_id"])
    duplicates = [group for group in fingerprints.values() if len(group) > 1]
    train_ids = {studies[index]["study_id"] for index in train_indices}
    test_ids = {studies[index]["study_id"] for index in test_indices}
    assert not train_ids & test_ids
    return {"study_count": len(studies), "group_definition": "Registry country list: India-only and US-only are mutually exclusive; shared studies occur once in a separate group, even if they also recruit in other countries.",
            "split_definition": "SHA256(UTF-8 study_id) interpreted as integer modulo 10; train <8, test >=8. No record or source study ID crosses splits.",
            "train_study_ids": sorted(train_ids), "test_study_ids": sorted(test_ids),
            "train_count": len(train_ids), "test_count": len(test_ids),
            "duplicate_eligibility_text_study_groups": duplicates,
            "textual_leakage_limitation": "Study-ID grouping prevents identical-study leakage. Exact normalized-text duplicates are audited; sponsor/protocol-family or near-duplicate prose is not clustered, so this is not proof of protocol independence.",
            "tfidf": {"fit_scope": "training study eligibility texts only", "vocabulary_size": len(vocabulary),
                      "stop_words": None, "negation_retained": True, "stemming": False, "lemmatization": False,
                      "normalization": "NFKC; casefold; offset-preserving tokens filtered to tokens with an alphanumeric character", "ngram_range": [1, 1]},
            "jsd_definition": "JSD(P,Q)=0.5 KL2(P||M)+0.5 KL2(Q||M), M=(P+Q)/2; empirical unigram token counts, no smoothing, union of observed vocabulary. All-descriptive JSD uses full text solely as a descriptive distribution comparison; test-only JSD uses test studies. It is not a fitted predictive feature or accuracy.",
            "groups": groups, "comparisons": comparisons,
            "interpretation": "Small convenience registry sample; coverage and lexical differences are descriptive, confounded by protocol mix, geography, study age and document style. These analyses implement no learned domain adaptation and cannot demonstrate regional extraction accuracy or generalization."}, rows


def performance(texts: list[str], repetitions: int) -> dict:
    for text in texts[:3]:
        extract(text)  # warm imports and compiled-regex cache, outside timing
    samples = []
    for _ in range(repetitions):
        for text in texts:
            started = time.perf_counter()
            extract(text)
            samples.append((time.perf_counter() - started) * 1000)
    process = psutil.Process()
    rss_before = process.memory_info().rss
    max_observed_rss = rss_before
    tracemalloc.start()
    for text in texts:
        output = extract(text)
        max_observed_rss = max(max_observed_rss, process.memory_info().rss)
        del output
    traced_current, traced_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"documents": len(texts), "timing_repetitions": repetitions, "timed_calls": len(samples),
            "warmed_wall_latency_ms": {"mean": statistics.mean(samples), "median": statistics.median(samples),
                                       "p95": float(np.percentile(samples, 95)), "max": max(samples)},
            "memory_separate_traced_pass": {"rss_before_bytes": rss_before, "max_observed_rss_bytes": max_observed_rss,
                                            "observed_rss_delta_bytes": max_observed_rss - rss_before,
                                            "tracemalloc_peak_bytes": traced_peak, "tracemalloc_retained_bytes": traced_current},
            "limitations": "Single process CPU wall time, serial warmed calls, no network/model retrieval/UI, not a load test. Memory tracing runs separately from latency. RSS is sampled after calls and includes interpreter/libraries; it is not a true OS peak or exclusive parser allocation. Tracemalloc observes Python allocations, not all native buffers."}


def profile_evaluation() -> dict:
    # Source wording, observations and statuses are explicit developer labels.
    cases = [
        ("Age >= 21 years", {"age": 21}, "MATCHES_KNOWN_CRITERIA"),
        ("Age > 21 years", {"age": 21}, "DOES_NOT_MATCH_KNOWN_CRITERIA"),
        ("Age <= 70 years", {"age": 70}, "MATCHES_KNOWN_CRITERIA"),
        ("Age < 70 years", {"age": 70}, "DOES_NOT_MATCH_KNOWN_CRITERIA"),
        ("Age between 21 and 70 years exclusive", {"age": 21}, "DOES_NOT_MATCH_KNOWN_CRITERIA"),
        ("Age >= 21 years", {}, "INSUFFICIENT_INFORMATION"),
        ("No T2DM", {"conditions": []}, "INSUFFICIENT_INFORMATION"),
        ("No T2DM", {"type_2_diabetes": False}, "MATCHES_KNOWN_CRITERIA"),
        ("Exclusion Criteria:\n- Pregnancy", {"pregnant": True}, "DOES_NOT_MATCH_KNOWN_CRITERIA"),
        ("Exclusion Criteria:\n- Pregnancy", {"pregnant": False}, "MATCHES_KNOWN_CRITERIA"),
        ("Age >= 21 years and BMI < 29 kg/m2", {"age": 23}, "INSUFFICIENT_INFORMATION"),
        ("Age >= 21 years or BMI < 29 kg/m2", {"age": 23}, "MATCHES_KNOWN_CRITERIA"),
        ("Age >= 21 years or BMI < 29 kg/m2", {"age": 19}, "INSUFFICIENT_INFORMATION"),
        ("Inclusion Criteria:\n- Age >= 21 years\n- Willing to attend visits", {"age": 23}, "INSUFFICIENT_INFORMATION"),
        ("Inclusion Criteria:\n- Age >= 21 years\n- Willing to attend visits", {"age": 19}, "DOES_NOT_MATCH_KNOWN_CRITERIA"),
        ("Age >= 21 years", {"age": {"value": 252, "unit": "months"}}, "MATCHES_KNOWN_CRITERIA"),
        ("Age >= 21 years", {"age": {"value": 23, "unit": "mg/dL"}}, "INSUFFICIENT_INFORMATION"),
        ("Age > 70 years\n\nAge <= 70 years", {"age": 45}, "INSUFFICIENT_INFORMATION"),
    ]
    rows = []
    for index, (text, attributes, expected) in enumerate(cases, 1):
        parsed = extract(text, f"SYNTHETIC-PROFILE-REF-{index}")
        profile = {"is_synthetic": True, **attributes}
        result = evaluate_profile(profile, parsed["rules"], parsed["unresolved"])
        rows.append({"case_id": f"PROFILE-DEVREF-{index:03d}", "source_text": text,
                     "profile": profile, "expected_status": expected, "predicted_status": result["status"], "correct": result["status"] == expected})
    return {"label_origin": "developer_reference", "expert_reviewed": False,
            "scope": "End-to-end extraction plus three-valued synthetic profile comparison, including boundary, missingness, negation, unresolved criteria, unit and contradiction cases. No patient outcomes or clinical eligibility labels.",
            "status_accuracy": ratio(sum(row["correct"] for row in rows), len(rows)), "cases": rows}


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value for key, value in row.items()})


def plots(report: dict, output_dir: Path) -> None:
    plt.rcParams.update({"font.size": 10, "figure.dpi": 130})
    reference = report["developer_reference"]["all"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.3), constrained_layout=True)
    labels = list(DIMENSIONS) + ["full rule"]
    measures = [reference["component_case_exact_accuracy"][dimension] for dimension in DIMENSIONS] + [reference["full_rule_match_expected_executable"]]
    values = [100 * measure["value"] if measure["value"] is not None else 0 for measure in measures]
    axes[0].barh(labels, values, color="#25638b")
    axes[0].set(xlim=(0, 118), xlabel="Whole-case exact match (%)", title="Developer references: expected executable cases")
    for i, measure in enumerate(measures):
        axes[0].text(values[i] + 1, i, f'{measure["numerator"]}/{measure["denominator"]}', va="center", fontsize=8)
    confusion = reference["confusion"]
    cells = np.array([[confusion["TP"], confusion["FN"]], [confusion["FP"], confusion["TN"]]])
    axes[1].imshow(cells, cmap="Blues")
    axes[1].set(xticks=[0, 1], xticklabels=["Executable", "Abstain"], yticks=[0, 1], yticklabels=["Executable", "Unsupported"], xlabel="Parser output", ylabel="Developer expectation", title="Complete-representation confusion counts")
    for (i, j), value in np.ndenumerate(cells):
        axes[1].text(j, i, str(value), ha="center", va="center", fontsize=20, color="white" if value > cells.max() / 2 else "black")
    fig.suptitle("Synthetic engineering references; no expert clinical ground truth", fontsize=11)
    fig.savefig(output_dir / "developer_reference_metrics.png")
    plt.close(fig)
    regional = report["regional_exploration"]
    names = list(regional["groups"])
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    cov = [100 * (regional["groups"][name]["micro_criterion_coverage"]["value"] or 0) for name in names]
    display = [name.replace("_", " ") + f' (n={regional["groups"][name]["study_count"]})' for name in names]
    axes[0].bar(display, cov, color=["#c1762a", "#327eb2", "#5f9560"])
    axes[0].set(ylabel="Parsed criteria / all segmented criteria (%)", title="Registry parser coverage (not accuracy)", ylim=(0, max(cov + [5]) * 1.35))
    for i, name in enumerate(names):
        group = regional["groups"][name]
        axes[0].text(i, cov[i] + .25, f'{group["parsed_rules"]}/{group["criteria"]}', ha="center")
    comparisons = [item for item in regional["comparisons"] if item["scope"] == "all_descriptive"]
    axes[1].bar([item["left"].replace("_", " ") + "\nvs " + item["right"].replace("_", " ") for item in comparisons], [item["unigram_js_divergence_base2"] or 0 for item in comparisons], color="#6c629b")
    axes[1].set(ylabel="Unigram JSD (base 2; 0–1)", title="Descriptive lexical distribution differences", ylim=(0, 1))
    fig.suptitle(f'{regional["study_count"]}-study convenience sample; regional labeled extraction accuracy unavailable', fontsize=11)
    fig.savefig(output_dir / "regional_coverage_and_shift.png")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--studies", type=Path, default=ROOT / "data/processed/studies.json")
    parser.add_argument("--references", type=Path, default=ROOT / "data/annotations/developer_reference_cases.json")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/research_metrics.json")
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    studies = json.loads(args.studies.read_text(encoding="utf-8"))
    reference, reference_rows = evaluate_references(args.references)
    regional, regional_rows = regional_evaluation(studies)
    report = {"schema_version": "research-evaluation-v1", "generated_at": datetime.now(timezone.utc).isoformat(),
              "inputs": {"studies": str(args.studies.relative_to(ROOT)) if args.studies.is_relative_to(ROOT) else str(args.studies),
                         "studies_sha256": hashlib.sha256(args.studies.read_bytes()).hexdigest(),
                         "references_sha256": hashlib.sha256(args.references.read_bytes()).hexdigest(),
                         "parser_sha256": hashlib.sha256((ROOT / "backend/app/nlp.py").read_bytes()).hexdigest()},
              "environment": {"python": sys.version, "platform": platform.platform(), "processor": platform.processor(),
                              "packages": {package: importlib.metadata.version(package) for package in ("numpy", "scikit-learn", "matplotlib", "psutil")}},
              "developer_reference": reference, "synthetic_profile_reference": profile_evaluation(),
              "regional_exploration": regional,
              "parser_performance_registry": performance([study["eligibility_text"] for study in studies], args.repetitions),
              "limitations": ["Developer-authored, not blinded, not expert-adjudicated references; no clinical accuracy or external validity estimate.",
                              "No regional labeled gold: regional extraction accuracy, FPR/FNR, patient eligibility accuracy and clinical utility remain unavailable.",
                              "Small nonrandom English-language CTgov sample; country of recruitment is not participant ethnicity, healthcare system, or a national corpus.",
                              "Descriptive vocabulary shift and parser coverage are not learned domain adaptation or a causal regional effect.",
                              "Profile results concern explicit synthetic inputs only. Real-world review is always required."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_dir = args.output.parent / "research"
    output_dir.mkdir(exist_ok=True)
    write_csv(output_dir / "developer_reference_predictions.csv", reference_rows)
    write_csv(output_dir / "regional_per_study.csv", regional_rows)
    plots(report, output_dir)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output), "developer_references": reference["all"],
                      "profile_status_accuracy": report["synthetic_profile_reference"]["status_accuracy"],
                      "regional_coverage": {name: group["micro_criterion_coverage"] for name, group in regional["groups"].items()},
                      "performance": report["parser_performance_registry"]}, indent=2))


if __name__ == "__main__":
    main()
