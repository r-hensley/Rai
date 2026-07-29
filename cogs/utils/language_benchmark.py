"""Offline benchmark harness for Rai's English/Spanish language detectors.

This module is deliberately independent of Discord and bot globals.  It can be
called from Python or run as a CLI:

    python -m cogs.utils.language_benchmark list-detectors
    python -m cogs.utils.language_benchmark learning-curve
    python -m cogs.utils.language_benchmark run \
        --raw-corpus cogs/utils \
        --cleaned-corpus cogs/utils/corpus/audit_cleaned_2026_07_27 \
        --output-dir .codex/language-benchmark

The benchmark uses a fixed, normalized-text-grouped evaluation set from the
cleaned corpus.  Exact text groups with contradictory labels are excluded from
evaluation, and all evaluation texts are excluded from every trainable model's
training data.  This avoids the substantial duplicate leakage in the source
corpora and makes raw-versus-cleaned training comparisons fair.

Only local, offline detectors are supported.  Optional package adapters are
loaded lazily by :mod:`cogs.utils.language_benchmark_detectors`.
"""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import math
import os
import platform
import random
import statistics
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from cogs.utils import language_benchmark_detectors as detector_adapters


CORPUS_LABELS: dict[str, str] = {
    "advanced.csv": "en",
    "beginner.csv": "en",
    "avanzado.csv": "es",
    "principiante.csv": "es",
}

VIEWS: dict[str, tuple[str, ...]] = {
    "all": ("advanced.csv", "beginner.csv", "avanzado.csv", "principiante.csv"),
    "beginner": ("beginner.csv", "principiante.csv"),
    "advanced": ("advanced.csv", "avanzado.csv"),
}

SCENARIOS: dict[str, tuple[str, str]] = {
    "all": ("all", "all"),
    "beginner": ("beginner", "beginner"),
    "advanced": ("advanced", "advanced"),
    "beginner_to_advanced": ("beginner", "advanced"),
    "advanced_to_beginner": ("advanced", "beginner"),
}

DEFAULT_NGRAM_RANGES: tuple[tuple[int, int], ...] = (
    (2, 2),
    (3, 3),
    (2, 4),
    (2, 5),
)

DEFAULT_PACKAGE_DETECTORS: tuple[str, ...] = (
    "langdetect",
    "langdetect_binary",
    "lingua_binary",
    "lingua_10",
    "lingua_all",
    "langid",
    "pycld2",
    "gcld3",
    "cld3",
)


@dataclass(frozen=True)
class CorpusRecord:
    source_file: str
    source_line: int
    text: str
    label: str
    normalized_text: str

    @property
    def characters(self) -> int:
        return len(self.text.strip())


@dataclass(frozen=True)
class EvaluationSet:
    view: str
    records: tuple[CorpusRecord, ...]
    normalized_keys: frozenset[str]
    conflicting_group_count: int
    available_unique_by_label: Mapping[str, int]
    selected_by_label: Mapping[str, int]
    digest: str


@dataclass(frozen=True)
class LocalRunSpec:
    detector: str
    training_corpus: str
    scenario: str
    ngram_range: tuple[int, int]
    training_min_chars: int = 0


@dataclass
class BenchmarkConfig:
    raw_corpus: Path
    cleaned_corpus: Path
    output_dir: Path
    seed: int = 42
    evaluation_per_language: int = 1500
    latency_sample_size: int = 100
    ngram_ranges: tuple[tuple[int, int], ...] = DEFAULT_NGRAM_RANGES
    local_detectors: tuple[str, ...] = ("rai_current_nb", "rai_legacy_nb")
    package_detectors: tuple[str, ...] = DEFAULT_PACKAGE_DETECTORS
    include_lingua_all: bool = False
    max_error_examples_per_run: int = 8


@dataclass
class RunArtifacts:
    results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def normalize_text(text: str) -> str:
    """Normalize enough to group duplicate messages without changing labels."""

    normalized = unicodedata.normalize("NFKC", text).casefold().strip()
    return " ".join(normalized.split())


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def corpus_hashes(corpus_dir: Path) -> dict[str, str]:
    return {
        filename: file_sha256(corpus_dir / filename)
        for filename in CORPUS_LABELS
    }


def load_corpus_records(
    corpus_dir: Path,
    view: str = "all",
    *,
    min_chars: int = 0,
) -> list[CorpusRecord]:
    if view not in VIEWS:
        raise ValueError(f"Unknown corpus view {view!r}; choose from {sorted(VIEWS)}")

    records: list[CorpusRecord] = []
    for filename in VIEWS[view]:
        path = corpus_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing corpus file: {path}")
        with path.open(newline="", encoding="utf-8") as source:
            reader = csv.reader(source, delimiter=" ", quotechar="|")
            for line_number, row in enumerate(reader, 1):
                if len(row) != 3:
                    raise ValueError(
                        f"{path}:{line_number} has {len(row)} fields; expected 3"
                    )
                text = row[2]
                if len(text.strip()) < min_chars:
                    continue
                normalized = normalize_text(text)
                if not normalized:
                    continue
                records.append(
                    CorpusRecord(
                        source_file=filename,
                        source_line=line_number,
                        text=text,
                        label=CORPUS_LABELS[filename],
                        normalized_text=normalized,
                    )
                )
    return records


def build_evaluation_set(
    cleaned_corpus: Path,
    view: str,
    *,
    seed: int,
    per_language: int,
) -> EvaluationSet:
    """Select one representative per normalized text, stratified by label."""

    grouped: dict[str, list[CorpusRecord]] = defaultdict(list)
    for record in load_corpus_records(cleaned_corpus, view):
        grouped[record.normalized_text].append(record)

    candidates: dict[str, list[CorpusRecord]] = {"en": [], "es": []}
    conflicting = 0
    for normalized, group in grouped.items():
        labels = {record.label for record in group}
        if len(labels) != 1:
            conflicting += 1
            continue
        label = next(iter(labels))
        representative = min(
            group,
            key=lambda record: (record.source_file, record.source_line),
        )
        candidates[label].append(representative)

    rng = random.Random(f"{seed}:{view}")
    selected: list[CorpusRecord] = []
    selected_counts: dict[str, int] = {}
    available_counts = {label: len(rows) for label, rows in candidates.items()}
    for label in ("en", "es"):
        rows = sorted(
            candidates[label],
            key=lambda record: (record.normalized_text, record.source_file, record.source_line),
        )
        take = min(per_language, len(rows))
        chosen = rng.sample(rows, take)
        selected.extend(chosen)
        selected_counts[label] = take

    rng.shuffle(selected)
    digest_source = "\n".join(
        f"{record.label}\t{record.normalized_text}"
        for record in sorted(selected, key=lambda item: (item.label, item.normalized_text))
    )
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
    return EvaluationSet(
        view=view,
        records=tuple(selected),
        normalized_keys=frozenset(record.normalized_text for record in selected),
        conflicting_group_count=conflicting,
        available_unique_by_label=available_counts,
        selected_by_label=selected_counts,
        digest=digest,
    )


def _training_variant(config: BenchmarkConfig, name: str) -> tuple[Path, int]:
    if name == "raw":
        return config.raw_corpus, 0
    if name == "cleaned":
        return config.cleaned_corpus, 0
    if name == "cleaned_min10":
        return config.cleaned_corpus, 10
    if name == "cleaned_min16":
        return config.cleaned_corpus, 16
    raise ValueError(f"Unknown training corpus variant: {name}")


def prepare_training_data(
    config: BenchmarkConfig,
    training_corpus: str,
    train_view: str,
    evaluation: EvaluationSet,
) -> tuple[list[str], list[str], dict[str, Any]]:
    corpus_dir, min_chars = _training_variant(config, training_corpus)
    all_records = load_corpus_records(corpus_dir, train_view, min_chars=min_chars)
    retained = [
        record
        for record in all_records
        if record.normalized_text not in evaluation.normalized_keys
    ]
    texts = [record.text for record in retained]
    labels = [record.label for record in retained]
    counts = Counter(labels)
    metadata = {
        "training_rows": len(retained),
        "training_english": counts["en"],
        "training_spanish": counts["es"],
        "excluded_evaluation_occurrences": len(all_records) - len(retained),
        "training_min_chars": min_chars,
    }
    return texts, labels, metadata


def standard_local_plan(config: BenchmarkConfig) -> list[LocalRunSpec]:
    """The default matrix balances coverage with practical local runtime."""

    plan: list[LocalRunSpec] = []
    within_scenarios = ("all", "beginner", "advanced")
    for detector in config.local_detectors:
        for corpus_name in ("raw", "cleaned"):
            for scenario in within_scenarios:
                for ngram_range in config.ngram_ranges:
                    plan.append(
                        LocalRunSpec(
                            detector=detector,
                            training_corpus=corpus_name,
                            scenario=scenario,
                            ngram_range=ngram_range,
                        )
                    )

    if "rai_current_nb" in config.local_detectors:
        for corpus_name, minimum in (("cleaned_min10", 10), ("cleaned_min16", 16)):
            for ngram_range in config.ngram_ranges:
                plan.append(
                    LocalRunSpec(
                        detector="rai_current_nb",
                        training_corpus=corpus_name,
                        scenario="all",
                        ngram_range=ngram_range,
                        training_min_chars=minimum,
                    )
                )
        for scenario in ("beginner_to_advanced", "advanced_to_beginner"):
            for ngram_range in config.ngram_ranges:
                plan.append(
                    LocalRunSpec(
                        detector="rai_current_nb",
                        training_corpus="cleaned",
                        scenario=scenario,
                        ngram_range=ngram_range,
                    )
                )
    return plan


def _percentile(samples: Sequence[float], percentile: float) -> float | None:
    if not samples:
        return None
    ordered = sorted(samples)
    index = (len(ordered) - 1) * percentile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def _rss_bytes() -> int | None:
    try:
        import psutil  # type: ignore

        return int(psutil.Process(os.getpid()).memory_info().rss)
    except (ImportError, OSError):
        return None


def _adapter_metadata(detector: Any) -> dict[str, Any]:
    value = getattr(detector, "metadata", {})
    if callable(value):
        value = value()
    return dict(value or {})


def _serialized_size(detector: Any) -> int | None:
    method = getattr(detector, "serialized_size_bytes", None)
    if not callable(method):
        return None
    try:
        return int(method())
    except Exception:
        return None


def _time_detector(
    detector: Any,
    evaluation_records: Sequence[CorpusRecord],
    *,
    latency_sample_size: int,
    measure_first_prediction: bool = True,
) -> tuple[list[str], dict[str, Any]]:
    texts = [record.text for record in evaluation_records]
    if not texts:
        return [], {
            "first_prediction_ms": None,
            "prediction_seconds": 0.0,
            "messages_per_second": None,
            "latency_p50_ms": None,
            "latency_p95_ms": None,
            "latency_p99_ms": None,
            "timing_examples": 0,
        }

    first_ms = None
    if measure_first_prediction:
        first_start = time.perf_counter()
        detector.predict([texts[0]])
        first_ms = (time.perf_counter() - first_start) * 1000

    start = time.perf_counter()
    predictions = list(detector.predict(texts))
    predict_seconds = time.perf_counter() - start

    latency_samples: list[float] = []
    sample_count = min(latency_sample_size, len(texts))
    if sample_count:
        step = max(1, len(texts) // sample_count)
        for text in texts[::step][:sample_count]:
            sample_start = time.perf_counter()
            detector.predict([text])
            latency_samples.append((time.perf_counter() - sample_start) * 1000)

    return predictions, {
        "first_prediction_ms": first_ms,
        "prediction_seconds": predict_seconds,
        "messages_per_second": (
            len(texts) / predict_seconds if predict_seconds > 0 else None
        ),
        "latency_p50_ms": _percentile(latency_samples, 0.50),
        "latency_p95_ms": _percentile(latency_samples, 0.95),
        "latency_p99_ms": _percentile(latency_samples, 0.99),
        "timing_examples": len(texts),
    }


def _safe_div(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    return numerator / denominator


def classification_metrics(
    truth: Sequence[str],
    predictions: Sequence[str],
) -> dict[str, Any]:
    if len(truth) != len(predictions):
        raise ValueError(
            f"Prediction count {len(predictions)} does not match truth count {len(truth)}"
        )
    total = len(truth)
    covered = sum(prediction in {"en", "es"} for prediction in predictions)
    correct = sum(actual == prediction for actual, prediction in zip(truth, predictions))
    covered_correct = sum(
        actual == prediction
        for actual, prediction in zip(truth, predictions)
        if prediction in {"en", "es"}
    )

    result: dict[str, Any] = {
        "examples": total,
        "correct": correct,
        "accuracy": _safe_div(correct, total),
        "coverage": _safe_div(covered, total),
        "covered_accuracy": _safe_div(covered_correct, covered),
        "abstentions": total - covered,
    }

    f1_values: list[float] = []
    for label in ("en", "es"):
        tp = sum(
            actual == label and prediction == label
            for actual, prediction in zip(truth, predictions)
        )
        fp = sum(
            actual != label and prediction == label
            for actual, prediction in zip(truth, predictions)
        )
        fn = sum(
            actual == label and prediction != label
            for actual, prediction in zip(truth, predictions)
        )
        tn = sum(
            actual != label and prediction != label
            for actual, prediction in zip(truth, predictions)
        )
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        if precision is None or recall is None or precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2 * precision * recall / (precision + recall)
        f1_values.append(f1)
        result.update(
            {
                f"{label}_tp": tp,
                f"{label}_fp": fp,
                f"{label}_fn": fn,
                f"{label}_tn": tn,
                f"{label}_precision": precision,
                f"{label}_recall": recall,
                f"{label}_f1": f1,
                f"{label}_false_positive_rate": _safe_div(fp, fp + tn),
            }
        )
    result["macro_f1"] = statistics.fmean(f1_values) if f1_values else None
    return result


def _bucket_indexes(records: Sequence[CorpusRecord]) -> dict[str, list[int]]:
    buckets: dict[str, list[int]] = {
        "all": [],
        "<10": [],
        "10-15": [],
        "16-30": [],
        "31+": [],
        "16+": [],
    }
    for index, record in enumerate(records):
        length = record.characters
        buckets["all"].append(index)
        if length < 10:
            buckets["<10"].append(index)
        elif length <= 15:
            buckets["10-15"].append(index)
        elif length <= 30:
            buckets["16-30"].append(index)
            buckets["16+"].append(index)
        else:
            buckets["31+"].append(index)
            buckets["16+"].append(index)
    return buckets


def metric_rows(
    base: Mapping[str, Any],
    records: Sequence[CorpusRecord],
    predictions: Sequence[str],
    overall_timing: Mapping[str, Any],
    *,
    detector: Any,
    latency_sample_size: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    buckets = _bucket_indexes(records)
    for bucket, indexes in buckets.items():
        if not indexes:
            continue
        truth = [records[index].label for index in indexes]
        predicted = [predictions[index] for index in indexes]
        row = dict(base)
        if bucket == "all":
            row.update(overall_timing)
            row["timing_scope"] = "all"
        elif bucket == "16+":
            bucket_records = [records[index] for index in indexes]
            _, bucket_timing = _time_detector(
                detector,
                bucket_records,
                latency_sample_size=latency_sample_size,
                measure_first_prediction=False,
            )
            row.update(bucket_timing)
            row["timing_scope"] = "16+"
        else:
            # Do not attach whole-evaluation timing to a different-sized
            # subset. Detailed accuracy is still reported for these buckets.
            row["timing_scope"] = "not_timed"
        row["length_bucket"] = bucket
        row.update(classification_metrics(truth, predicted))
        rows.append(row)
    return rows


def error_examples(
    base: Mapping[str, Any],
    records: Sequence[CorpusRecord],
    predictions: Sequence[str],
    limit: int,
) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for record, prediction in zip(records, predictions):
        if prediction == record.label:
            continue
        examples.append(
            {
                **base,
                "source_file": record.source_file,
                "source_line": record.source_line,
                "characters": record.characters,
                "truth": record.label,
                "prediction": prediction,
                "text": record.text,
            }
        )
        if len(examples) >= limit:
            break
    return examples


def run_local_benchmarks(
    config: BenchmarkConfig,
    evaluations: Mapping[str, EvaluationSet],
    artifacts: RunArtifacts,
) -> None:
    for run_number, spec in enumerate(standard_local_plan(config), 1):
        train_view, eval_view = SCENARIOS[spec.scenario]
        evaluation = evaluations[eval_view]
        print(
            f"[local {run_number}] {spec.detector} corpus={spec.training_corpus} "
            f"scenario={spec.scenario} ngram={spec.ngram_range}",
            flush=True,
        )
        try:
            texts, labels, training_meta = prepare_training_data(
                config,
                spec.training_corpus,
                train_view,
                evaluation,
            )
            rss_before = _rss_bytes()
            creation_start = time.perf_counter()
            detector = detector_adapters.create_detector(
                spec.detector,
                ngram_range=spec.ngram_range,
                seed=config.seed,
            )
            adapter_creation_seconds = time.perf_counter() - creation_start
            initialization_start = time.perf_counter()
            detector.initialize()
            initialization_seconds = time.perf_counter() - initialization_start
            rss_after_initialize = _rss_bytes()
            fit_start = time.perf_counter()
            detector.fit(texts, labels)
            training_seconds = time.perf_counter() - fit_start
            rss_after_fit = _rss_bytes()
            predictions, timing = _time_detector(
                detector,
                evaluation.records,
                latency_sample_size=config.latency_sample_size,
            )
            rss_after_predict = _rss_bytes()
            adapter_meta = _adapter_metadata(detector)
            base = {
                "detector": spec.detector,
                "detector_kind": "trainable",
                "training_corpus": spec.training_corpus,
                "scenario": spec.scenario,
                "train_view": train_view,
                "evaluation_view": eval_view,
                "ngram_min": spec.ngram_range[0],
                "ngram_max": spec.ngram_range[1],
                "evaluation_digest": evaluation.digest,
                "adapter_creation_seconds": adapter_creation_seconds,
                "initialization_seconds": initialization_seconds,
                "build_seconds": (
                    adapter_creation_seconds + initialization_seconds
                ),
                "training_seconds": training_seconds,
                "rss_before_bytes": rss_before,
                "rss_after_initialize_bytes": rss_after_initialize,
                "rss_after_fit_bytes": rss_after_fit,
                "rss_after_predict_bytes": rss_after_predict,
                "rss_initialize_delta_bytes": (
                    rss_after_initialize - rss_before
                    if rss_before is not None and rss_after_initialize is not None
                    else None
                ),
                "rss_fit_delta_bytes": (
                    rss_after_fit - rss_before
                    if rss_before is not None and rss_after_fit is not None
                    else None
                ),
                "rss_total_delta_bytes": (
                    rss_after_predict - rss_before
                    if rss_before is not None and rss_after_predict is not None
                    else None
                ),
                "serialized_model_bytes": _serialized_size(detector),
                **training_meta,
                **{f"adapter_{key}": value for key, value in adapter_meta.items()},
            }
            artifacts.results.extend(
                metric_rows(
                    base,
                    evaluation.records,
                    predictions,
                    timing,
                    detector=detector,
                    latency_sample_size=config.latency_sample_size,
                )
            )
            artifacts.errors.extend(
                error_examples(
                    {
                        key: base[key]
                        for key in (
                            "detector",
                            "training_corpus",
                            "scenario",
                            "ngram_min",
                            "ngram_max",
                        )
                    },
                    evaluation.records,
                    predictions,
                    config.max_error_examples_per_run,
                )
            )
        except Exception as exc:
            artifacts.skipped.append(
                {
                    "detector": spec.detector,
                    "training_corpus": spec.training_corpus,
                    "scenario": spec.scenario,
                    "ngram_range": list(spec.ngram_range),
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"  skipped: {type(exc).__name__}: {exc}", flush=True)
        finally:
            save_artifacts(config, artifacts)
            if "detector" in locals():
                del detector
            gc.collect()


def _available_package_names(config: BenchmarkConfig) -> list[str]:
    requested = list(config.package_detectors)
    if not config.include_lingua_all:
        requested = [name for name in requested if name != "lingua_all"]
    return requested


def run_package_benchmarks(
    config: BenchmarkConfig,
    evaluations: Mapping[str, EvaluationSet],
    artifacts: RunArtifacts,
) -> None:
    for detector_name in _available_package_names(config):
        for eval_view in ("all", "beginner", "advanced"):
            evaluation = evaluations[eval_view]
            print(f"[package] {detector_name} evaluation={eval_view}", flush=True)
            try:
                rss_before = _rss_bytes()
                creation_start = time.perf_counter()
                detector = detector_adapters.create_detector(
                    detector_name,
                    seed=config.seed,
                )
                adapter_creation_seconds = time.perf_counter() - creation_start
                initialization_start = time.perf_counter()
                detector.initialize()
                initialization_seconds = time.perf_counter() - initialization_start
                rss_after_initialize = _rss_bytes()
                detector.fit([], [])
                rss_after_fit = _rss_bytes()
                predictions, timing = _time_detector(
                    detector,
                    evaluation.records,
                    latency_sample_size=config.latency_sample_size,
                )
                rss_after_predict = _rss_bytes()
                adapter_meta = _adapter_metadata(detector)
                base = {
                    "detector": detector_name,
                    "detector_kind": "pretrained_package",
                    "training_corpus": "pretrained",
                    "scenario": f"package_{eval_view}",
                    "train_view": None,
                    "evaluation_view": eval_view,
                    "ngram_min": None,
                    "ngram_max": None,
                    "evaluation_digest": evaluation.digest,
                    "adapter_creation_seconds": adapter_creation_seconds,
                    "initialization_seconds": initialization_seconds,
                    "build_seconds": (
                        adapter_creation_seconds + initialization_seconds
                    ),
                    "training_seconds": 0.0,
                    "training_rows": 0,
                    "training_english": 0,
                    "training_spanish": 0,
                    "training_min_chars": None,
                    "excluded_evaluation_occurrences": 0,
                    "rss_before_bytes": rss_before,
                    "rss_after_initialize_bytes": rss_after_initialize,
                    "rss_after_fit_bytes": rss_after_fit,
                    "rss_after_predict_bytes": rss_after_predict,
                    "rss_initialize_delta_bytes": (
                        rss_after_initialize - rss_before
                        if rss_before is not None and rss_after_initialize is not None
                        else None
                    ),
                    "rss_fit_delta_bytes": (
                        rss_after_fit - rss_before
                        if rss_before is not None and rss_after_fit is not None
                        else None
                    ),
                    "rss_total_delta_bytes": (
                        rss_after_predict - rss_before
                        if rss_before is not None and rss_after_predict is not None
                        else None
                    ),
                    "serialized_model_bytes": _serialized_size(detector),
                    **{f"adapter_{key}": value for key, value in adapter_meta.items()},
                }
                artifacts.results.extend(
                    metric_rows(
                        base,
                        evaluation.records,
                        predictions,
                        timing,
                        detector=detector,
                        latency_sample_size=config.latency_sample_size,
                    )
                )
                artifacts.errors.extend(
                    error_examples(
                        {
                            "detector": detector_name,
                            "training_corpus": "pretrained",
                            "scenario": f"package_{eval_view}",
                            "ngram_min": None,
                            "ngram_max": None,
                        },
                        evaluation.records,
                        predictions,
                        config.max_error_examples_per_run,
                    )
                )
            except Exception as exc:
                artifacts.skipped.append(
                    {
                        "detector": detector_name,
                        "training_corpus": "pretrained",
                        "scenario": f"package_{eval_view}",
                        "ngram_range": None,
                        "reason": f"{type(exc).__name__}: {exc}",
                    }
                )
                print(f"  skipped: {type(exc).__name__}: {exc}", flush=True)
                # An unavailable package will be unavailable for all views.
                if isinstance(
                    exc,
                    detector_adapters.DetectorUnavailableError,
                ):
                    break
            finally:
                save_artifacts(config, artifacts)
                if "detector" in locals():
                    del detector
                gc.collect()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    keys: list[str] = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in keys})


def _format_percent(value: Any) -> str:
    if value is None:
        return "—"
    return f"{100 * float(value):.2f}%"


def _format_seconds(value: Any) -> str:
    if value is None:
        return "—"
    return f"{float(value):.3f}"


def _format_mebibytes(value: Any) -> str:
    if value is None:
        return "—"
    return f"{float(value) / (1024 * 1024):.2f}"


def _append_ranked_table(
    lines: list[str],
    *,
    title: str,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    lines.extend(
        [
            f"### {title}",
            "",
            "| Rank | Detector | Training | N-grams | Accuracy | Macro F1 | Coverage | Covered accuracy | msg/s | Init s | Fit s | Model MiB |",
            "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    if not rows:
        lines.extend(["| — | No completed runs | — | — | — | — | — | — | — | — | — | — |", ""])
        return

    ranked = sorted(
        rows,
        key=lambda row: (
            row.get("macro_f1") is not None,
            row.get("macro_f1") or -1,
            row.get("messages_per_second") or -1,
        ),
        reverse=True,
    )
    for rank, row in enumerate(ranked[:30], 1):
        ngram = (
            "—"
            if row.get("ngram_min") is None
            else f"({row['ngram_min']},{row['ngram_max']})"
        )
        throughput = row.get("messages_per_second")
        throughput_text = "—" if throughput is None else f"{float(throughput):.1f}"
        lines.append(
            f"| {rank} | {row['detector']} | {row['training_corpus']} | "
            f"{ngram} | {_format_percent(row.get('accuracy'))} | "
            f"{_format_percent(row.get('macro_f1'))} | "
            f"{_format_percent(row.get('coverage'))} | "
            f"{_format_percent(row.get('covered_accuracy'))} | "
            f"{throughput_text} | "
            f"{_format_seconds(row.get('initialization_seconds'))} | "
            f"{_format_seconds(row.get('training_seconds'))} | "
            f"{_format_mebibytes(row.get('serialized_model_bytes'))} |"
        )
    lines.append("")


def render_markdown_report(artifacts: RunArtifacts) -> str:
    overall = [
        row
        for row in artifacts.results
        if row.get("length_bucket") == "all"
    ]
    production = [
        row
        for row in artifacts.results
        if row.get("length_bucket") == "16+"
        and row.get("evaluation_view") == "all"
    ]
    binary_rows = [
        row
        for row in production
        if row.get("adapter_scope") == "English and Spanish"
    ]
    open_set_rows = [
        row
        for row in production
        if row.get("adapter_scope") != "English and Spanish"
    ]

    lines = [
        "# Rai language detector benchmark",
        "",
        f"Generated: {artifacts.metadata['generated_at']}",
        "",
        "All runs are local/offline. No API-backed or paid detector is invoked.",
        "",
        "## Evaluation design",
        "",
        (
            "Evaluation messages come from the audit-cleaned corpus, use one row per "
            "normalized text, exclude contradictory-label groups, and are excluded "
            "from every trainable model's training set. Package detectors are "
            "pretrained and receive the same fixed evaluation sets."
        ),
        "",
        "The production-oriented ranking below uses messages of at least 16 characters, "
        "matching Rai's current strict `len(stripped_msg) > 15` gate.",
        "",
        "Only the `all` evaluation view is ranked here, so every row in each table "
        "uses the same held-out messages. Binary-oracle and multilingual/open-set "
        "detectors are separated because they solve different problems.",
        "",
        "## Production-length results",
        "",
    ]
    _append_ranked_table(
        lines,
        title="Known English vs Spanish",
        rows=binary_rows,
    )
    _append_ranked_table(
        lines,
        title="Multilingual / open-set",
        rows=open_set_rows,
    )

    lines.extend(
        [
            "",
            "## Corpus and evaluation snapshots",
            "",
            f"- Raw corpus hashes: `{json.dumps(artifacts.metadata['raw_hashes'], sort_keys=True)}`",
            f"- Cleaned corpus hashes: `{json.dumps(artifacts.metadata['cleaned_hashes'], sort_keys=True)}`",
        ]
    )
    for view, metadata in artifacts.metadata["evaluation_sets"].items():
        lines.append(
            f"- `{view}`: {metadata['selected_by_label']} selected, "
            f"{metadata['conflicting_group_count']} conflicting normalized groups excluded, "
            f"digest `{metadata['digest']}`"
        )

    lines.extend(
        [
            "",
            "## Runtime environment",
            "",
            f"- Python: `{artifacts.metadata['python_version']}`",
            f"- Executable: `{artifacts.metadata['python_executable']}`",
            f"- Platform: `{artifacts.metadata['platform']}`",
            (
                "- Timing and RSS are measured sequentially in one process after each "
                "adapter's explicit initialization. Shared interpreter/package caches "
                "can still affect later runs; use the figures as comparative local "
                "measurements, not isolated peak-memory guarantees."
            ),
            "",
            "## Artifacts",
            "",
            "- `results.csv`: every metric row and length bucket.",
            "- `results.json`: configuration, environment, results, and skipped runs.",
            "- `error_examples.jsonl`: a bounded sample of mistakes per run.",
            "",
            "## Skipped detectors or runs",
            "",
        ]
    )
    if artifacts.skipped:
        for skipped in artifacts.skipped:
            lines.append(
                f"- `{skipped.get('detector')}` / `{skipped.get('scenario')}`: "
                f"{skipped.get('reason')}"
            )
    else:
        lines.append("- None.")

    lines.extend(
        [
            "",
            "## Important limitation",
            "",
            (
                "The held-out labels are inferred from cleaned chat-channel corpora, "
                "not from an independently authored linguistic gold set. Results measure "
                "agreement with those labels and relative performance on this domain; "
                "they should not be read as universal language-identification accuracy."
            ),
            "",
            f"Completed metric rows: {len(artifacts.results)} "
            f"({len(overall)} overall rows, {len(production)} production-length rows).",
            "",
        ]
    )
    return "\n".join(lines)


def save_artifacts(config: BenchmarkConfig, artifacts: RunArtifacts) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(config.output_dir / "results.csv", artifacts.results)
    payload = {
        "metadata": artifacts.metadata,
        "config": _json_safe(asdict(config)),
        "results": artifacts.results,
        "skipped": artifacts.skipped,
    }
    (config.output_dir / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (config.output_dir / "error_examples.jsonl").open(
        "w", encoding="utf-8"
    ) as target:
        for example in artifacts.errors:
            target.write(json.dumps(example, ensure_ascii=False) + "\n")
    (config.output_dir / "report.md").write_text(
        render_markdown_report(artifacts),
        encoding="utf-8",
    )


def run_benchmark(config: BenchmarkConfig) -> RunArtifacts:
    for directory in (config.raw_corpus, config.cleaned_corpus):
        if not directory.is_dir():
            raise FileNotFoundError(f"Corpus directory does not exist: {directory}")

    evaluations = {
        view: build_evaluation_set(
            config.cleaned_corpus,
            view,
            seed=config.seed,
            per_language=config.evaluation_per_language,
        )
        for view in ("all", "beginner", "advanced")
    }
    artifacts = RunArtifacts()
    artifacts.metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "raw_corpus": str(config.raw_corpus.resolve()),
        "cleaned_corpus": str(config.cleaned_corpus.resolve()),
        "raw_hashes": corpus_hashes(config.raw_corpus),
        "cleaned_hashes": corpus_hashes(config.cleaned_corpus),
        "evaluation_sets": {
            view: {
                "selected_by_label": dict(evaluation.selected_by_label),
                "available_unique_by_label": dict(
                    evaluation.available_unique_by_label
                ),
                "conflicting_group_count": evaluation.conflicting_group_count,
                "digest": evaluation.digest,
            }
            for view, evaluation in evaluations.items()
        },
        "detector_inventory": detector_adapters.detector_specs(),
    }

    run_local_benchmarks(config, evaluations, artifacts)
    run_package_benchmarks(config, evaluations, artifacts)
    save_artifacts(config, artifacts)
    return artifacts


def parse_ngram_range(value: str) -> tuple[int, int]:
    separators = (":", ",", "-")
    for separator in separators:
        if separator in value:
            lower_text, upper_text = value.split(separator, 1)
            lower, upper = int(lower_text), int(upper_text)
            break
    else:
        lower = upper = int(value)
    if lower < 1 or upper < lower:
        raise argparse.ArgumentTypeError(
            f"Invalid n-gram range {value!r}; expected MIN:MAX with 1 <= MIN <= MAX"
        )
    return lower, upper


def parse_learning_fraction(value: str) -> float:
    try:
        fraction = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid training fraction {value!r}; expected 0 < FRACTION <= 1"
        ) from exc
    if not math.isfinite(fraction) or not 0 < fraction <= 1:
        raise argparse.ArgumentTypeError(
            f"Invalid training fraction {value!r}; expected 0 < FRACTION <= 1"
        )
    return fraction


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "list-detectors",
        help="Show offline detector adapters and whether their packages are available.",
    )

    run_parser = subparsers.add_parser("run", help="Run the standard benchmark matrix.")
    run_parser.add_argument("--raw-corpus", type=Path, default=Path("cogs/utils"))
    run_parser.add_argument(
        "--cleaned-corpus",
        type=Path,
        default=Path("cogs/utils/corpus/audit_cleaned_2026_07_27"),
    )
    run_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".codex/language-benchmark"),
    )
    run_parser.add_argument("--seed", type=int, default=42)
    run_parser.add_argument("--evaluation-per-language", type=int, default=1500)
    run_parser.add_argument("--latency-sample-size", type=int, default=100)
    run_parser.add_argument(
        "--ngrams",
        nargs="+",
        type=parse_ngram_range,
        default=list(DEFAULT_NGRAM_RANGES),
    )
    run_parser.add_argument(
        "--local-detectors",
        nargs="+",
        default=["rai_current_nb", "rai_legacy_nb"],
    )
    run_parser.add_argument(
        "--package-detectors",
        nargs="+",
        default=list(DEFAULT_PACKAGE_DETECTORS),
    )
    run_parser.add_argument(
        "--include-lingua-all",
        action="store_true",
        help="Also build Lingua's much larger all-language detector.",
    )
    run_parser.add_argument("--max-error-examples-per-run", type=int, default=8)

    curve_parser = subparsers.add_parser(
        "learning-curve",
        help="Estimate how detector quality changes as clean training data grows.",
        description=(
            "Train nested, normalized-text-grouped samples repeatedly and "
            "evaluate every point on one fixed held-out set."
        ),
    )
    curve_parser.add_argument(
        "--cleaned-corpus",
        type=Path,
        default=Path("cogs/utils/corpus/audit_cleaned_2026_07_27"),
    )
    curve_parser.add_argument(
        "--raw-corpus",
        type=Path,
        default=Path("cogs/utils"),
        help="Raw corpus location; only used with --training-variant raw.",
    )
    curve_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".codex/language-learning-curve"),
    )
    curve_parser.add_argument(
        "--training-variant",
        choices=("raw", "cleaned", "cleaned_min10", "cleaned_min16"),
        default="cleaned",
    )
    curve_parser.add_argument(
        "--training-view",
        choices=tuple(VIEWS),
        default="all",
    )
    curve_parser.add_argument(
        "--evaluation-view",
        choices=tuple(VIEWS),
        default="all",
    )
    curve_parser.add_argument(
        "--fractions",
        nargs="+",
        type=parse_learning_fraction,
        default=[0.1, 0.2, 0.4, 0.6, 0.8, 1.0],
        metavar="FRACTION",
        help=(
            "Nested training fractions in (0,1]; "
            "default: 0.1 0.2 0.4 0.6 0.8 1.0."
        ),
    )
    curve_parser.add_argument(
        "--repeats",
        type=int,
        default=5,
        help="Independent nested-sampling repetitions; default: 5.",
    )
    curve_parser.add_argument(
        "--detectors",
        nargs="+",
        default=["rai_current_nb", "rai_legacy_nb"],
        help=(
            "Trainable offline detector adapters; "
            "default: rai_current_nb rai_legacy_nb."
        ),
    )
    curve_parser.add_argument(
        "--ngrams",
        nargs="+",
        type=parse_ngram_range,
        default=[(2, 5)],
        help="Character n-gram ranges; default: 2:5.",
    )
    curve_parser.add_argument("--seed", type=int, default=42)
    curve_parser.add_argument("--evaluation-per-language", type=int, default=1500)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "list-detectors":
        print(json.dumps(detector_adapters.detector_specs(), indent=2))
        return 0

    if args.command == "learning-curve":
        from cogs.utils import language_learning_curve

        curve_config = language_learning_curve.LearningCurveConfig(
            cleaned_corpus=args.cleaned_corpus,
            raw_corpus=args.raw_corpus,
            output_dir=args.output_dir,
            training_variant=args.training_variant,
            training_view=args.training_view,
            evaluation_view=args.evaluation_view,
            fractions=tuple(args.fractions),
            repeats=args.repeats,
            detectors=tuple(args.detectors),
            ngram_ranges=tuple(args.ngrams),
            seed=args.seed,
            evaluation_per_language=args.evaluation_per_language,
        )
        curve_artifacts = language_learning_curve.run_learning_curve(
            curve_config
        )
        print(
            f"Wrote {len(curve_artifacts.results)} learning-curve metric rows "
            f"to {curve_config.output_dir}; "
            f"{len(curve_artifacts.skipped)} runs skipped."
        )
        return 0

    config = BenchmarkConfig(
        raw_corpus=args.raw_corpus,
        cleaned_corpus=args.cleaned_corpus,
        output_dir=args.output_dir,
        seed=args.seed,
        evaluation_per_language=args.evaluation_per_language,
        latency_sample_size=args.latency_sample_size,
        ngram_ranges=tuple(args.ngrams),
        local_detectors=tuple(args.local_detectors),
        package_detectors=tuple(args.package_detectors),
        include_lingua_all=args.include_lingua_all,
        max_error_examples_per_run=args.max_error_examples_per_run,
    )
    artifacts = run_benchmark(config)
    print(
        f"Wrote {len(artifacts.results)} metric rows to {config.output_dir}; "
        f"{len(artifacts.skipped)} runs skipped."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
