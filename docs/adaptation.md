# Frozen biomedical encoder: completed CHIA head adaptation

The experiment trains a real supervised BIO token classifier on published CHIA human annotations. The pinned biomedical DistilBERT encoder is frozen. Only the 5,383 parameters of a new `Linear(768, 7)` head are optimized. This is head adaptation to the CHIA entity ontology; it is not end-to-end transformer fine-tuning, eligibility-rule training, or India/US domain adaptation.

## Measured result

The completed single-seed run uses exactly the original entity benchmark's held-out documents. Study IDs, document IDs, SHA256 text hashes, and full mapped gold span tuples are checked before comparison. Exact category plus exact full span tuple determines a match. The test contains 20 studies, 40 documents and 328 unique gold spans.

| Method | Precision | Recall | Exact-span micro F1 | TP | FP | FN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Dictionary from 800 training studies | 0.3636 | 0.5122 | 0.4253 | 168 | 294 | 160 |
| Original biomedical transformer, no CHIA training | 0.1281 | 0.1250 | 0.1265 | 41 | 279 | 287 |
| Frozen encoder plus head trained on 100 CHIA studies | 0.2441 | 0.4695 | 0.3212 | 154 | 477 | 174 |

The adapted head improves F1 by 0.1946 over the original biomedical transformer, while remaining 0.1041 below the dictionary. The dictionary uses substantially more training studies, so this comparison does not isolate architecture under equal training data. The head has 477 false-positive spans and is not suitable as an autonomous eligibility decision system.

![Measured comparison](../reports/adaptation_comparison.png)

Epoch 8 was selected from eight scheduled epochs by the highest development exact-span F1 (0.3360); ties select the earlier epoch. There is no test-based threshold, epoch, or hyperparameter selection. Per-category test F1 is 0.4000 for Condition, 0.2857 for Drug and 0.1641 for Procedure.

![Training loss and development selection](../reports/adaptation_learning_curve.png)

## Data, splits and alignment

- Source: Kury et al. (2020), [Chia Annotated Datasets v2](https://doi.org/10.6084/m9.figshare.11855817.v2), `with_scope`, CC BY 4.0; [archive file 21728850](https://ndownloader.figshare.com/files/21728850).
- Downloaded archive SHA256: `b51ec05ba42a3805daf9581dd22a305986f7c5ae3ca4dad36b70d37970fb69b2`. Corpus files remain under the ignored `data/external/chia/` directory.
- The original 1,000 study IDs are sorted by `sha256('trialops-chia-v1:' + study_id)`. The first 800 form the original training partition; the last 200 form its held-out partition.
- The first 100 original-training studies are head training data (200 documents). The next 20 are development data (40 documents). The original benchmark's first 20 held-out studies remain the test (40 documents). These three study sets have zero overlap. Full study and document IDs are in the JSON report.
- Text is loaded with `read_bytes().decode('utf-8')` so CRLF offsets are preserved. Every selected BRAT annotation must reproduce its original mention text. Entire invalid documents are excluded rather than shifting offsets. No invalid documents occur in these selected 140 studies; this does not imply the full source corpus has no invalid documents.
- Only human Condition, Drug and Procedure annotations supervise the head. Every token uses its offset into original text. A unique contiguous annotation assigns B to the wordpiece starting at its annotated start and I to later pieces. Tokens intersecting overlapping/discontinuous annotations or crossing gold boundaries use loss ignore index -100. Other tokens receive O.
- Training has 23,499 wordpieces, of which 485 are ignored and 23,014 supervised. The report records 158 ignored development wordpieces and 124 test wordpieces for alignment diagnostics; ignored labels never remove gold spans from evaluation. There are 121/25/24 discontinuous raw annotations in train/dev/test.
- Full gold discontinuous spans remain in exact evaluation, although a contiguous BIO head cannot reproduce them. Source annotation counts can exceed the unique spans used by set-based exact matching.

Only train and development source documents are encoded before fitting and epoch selection. Test source documents are encoded after selecting the head. Windowing uses maximum length 512, stride 64 and batches of up to four windows; duplicate offset pairs use the window where that token has the greatest distance from its boundary.

## Training and runtime

The encoder is [`d4data/biomedical-ner-all`](https://huggingface.co/d4data/biomedical-ner-all) at revision `015a4050c9ac99722e61c547aa9b4282bcbedc7f`, loaded from the existing cache in offline mode. All encoder parameters have gradients disabled and its dropout remains in evaluation mode. Train-only feature means and standard deviations normalize frozen features. Class weights use the square root of inverse training-label frequency, capped at 10.

Python/NumPy/PyTorch seed is 17. CPU PyTorch uses deterministic algorithms and four threads. AdamW uses learning rate 0.001, weight decay 0.0001, token batch size 512 and eight scheduled epochs. The JSON includes all epoch training losses, development precision/recall/F1, seven class counts/weights and the selected checkpoint checksum.

The measured environment is Windows, Python 3.11.9, PyTorch 2.14.1+cpu, an AMD Ryzen 7 7435HS with 8 physical/16 logical cores and 23.69 GiB visible RAM. The run takes 39.21 seconds including model load, encoding, training and evaluation; optimizer training on precomputed features takes 0.588 seconds. Model load takes 5.22 seconds. Mean test encoder-plus-head time is 96.05 ms per document. The 50 ms sampled process RSS peak is 953.13 MiB, including imported libraries, encoder, features and head; it is not exclusive model memory or an exact allocator peak. These timings omit production API overhead and may vary by machine.

The saved head and feature normalization tensors are `models/adapted_chia_head/head.safetensors`, with a companion `manifest.json`. Weights and cached datasets are ignored by Git. The artifact is for experimental evaluation and is not connected to eligibility-rule execution.

## Reproduce

From the repository root on Windows, with the locked dependencies, downloaded CHIA source and cached pinned biomedical model already present:

```powershell
.\.venv\Scripts\python.exe -u experiments/adapt_entity_head.py --train-studies 100 --dev-studies 20 --epochs 8
.\.venv\Scripts\python.exe -m pytest tests/test_adaptation.py -q
```

The experiment requires the existing `reports/entity_benchmark.json` and `reports/experiments/entity_predictions.jsonl` to verify the original held-out test. Reproduce that original comparison with `experiments/entity_benchmark.py --test-studies 20` if needed. The model is loaded with `local_files_only=True`; missing weights fail explicitly.

Outputs are `reports/adaptation_benchmark.json` (provenance, IDs, metrics, predictions, hyperparameters, losses, timing and memory), `reports/adaptation_per_document.csv`, `reports/adaptation_learning_curve.png`, and `reports/adaptation_comparison.png`. The result is exploratory, uses one seed and one fixed subset, and does not establish clinical efficacy, calibration or regional generalization. Ontology differences and possible upstream pretraining exposure remain limitations. There is no defined span-level true-negative universe, so false-positive rate is null; precision and FP counts are reported instead.
