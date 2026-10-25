"""Synthetic checks for the experimental CHIA BIO head's offset contract."""
from pathlib import Path

import pytest
import torch

from experiments.adapt_entity_head import LABEL_IDS, align_labels, decode, evaluate
from experiments.entity_benchmark import annotations


def test_bio_alignment_keeps_wordpieces_and_ignores_ambiguous_tokens():
    offsets = [(0, 4), (5, 9), (9, 13), (14, 18), (19, 24), (25, 30)]
    gold = [
        ("Condition", ((5, 13),), "diabetes"),
        ("Drug", ((14, 18), (25, 30)), "drug other"),
        ("Procedure", ((19, 24),), "tests"),
        ("Condition", ((19, 24),), "tests"),
    ]
    labels, ignored = align_labels(offsets, gold)
    assert labels.tolist() == [0, LABEL_IDS["B-Condition"], LABEL_IDS["I-Condition"], -100, -100, -100]
    assert ignored == 3


def test_tokens_crossing_annotation_boundaries_are_ignored():
    labels, ignored = align_labels([(0, 8), (9, 13)], [("Drug", ((2, 8),), "formin")])
    assert labels.tolist() == [-100, 0]
    assert ignored == 1


def test_decode_merges_wordpieces_and_spaces_preserving_crlf_offsets():
    text = "type 2\r\ndiabetes and pain"
    offsets = [(0, 4), (5, 6), (8, 11), (11, 16), (17, 20), (21, 25)]
    ids = [LABEL_IDS[label] for label in
           ["B-Condition", "I-Condition", "I-Condition", "I-Condition", "O", "I-Condition"]]
    assert decode(offsets, ids, text) == {("Condition", ((0, 16),)), ("Condition", ((21, 25),))}


def test_annotation_validation_uses_original_crlf_and_rejects_bad_offsets(tmp_path: Path):
    text_path = tmp_path / "NCT_test.txt"
    annotation_path = text_path.with_suffix(".ann")
    text_path.write_bytes(b"Age\r\ndiabetes")
    annotation_path.write_text("T1\tCondition 5 13\tdiabetes\n", encoding="utf-8")
    original = text_path.read_bytes().decode("utf-8")
    assert annotations(annotation_path, original) == [("Condition", ((5, 13),), "diabetes")]
    with pytest.raises(ValueError):
        annotations(annotation_path, original.replace("\r\n", "\n"))


def test_exact_span_evaluation_counts_discontinuous_gold_as_missed():
    head = torch.nn.Linear(1, 7)
    with torch.no_grad():
        head.weight.zero_()
        head.bias.zero_()
        head.bias[LABEL_IDS["B-Condition"]] = 2
    docs = [{"study_id": "test", "document_id": "test_inc", "text": "pain ache",
             "offsets": [(0, 4), (5, 9)], "features": torch.zeros(2, 1), "encoder_ms": 1.0,
             "gold": [("Condition", ((0, 4),), "pain"),
                      ("Condition", ((0, 4), (5, 9)), "pain ache")]}]
    metrics, rows = evaluate(head, docs)
    assert (metrics["tp"], metrics["fp"], metrics["fn"]) == (1, 1, 1)
    assert metrics["f1"] == 0.5
    assert rows[0]["gold_count"] == 2
