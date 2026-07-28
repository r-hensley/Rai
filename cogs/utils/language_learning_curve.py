"""Offline learning curves for Rai's trainable language detectors.

The module estimates how model quality changes as more *unique* English and
Spanish chat messages are made available for training.  It deliberately uses
the fixed, grouped evaluation-set builder from :mod:`language_benchmark` and
never invokes an API or any network-backed service.

The important experimental unit is a normalized message, not a corpus row:

* every normalized evaluation key is removed from training;
* normalized groups carrying both labels are discarded;
* one deterministic representative is retained per remaining group;
* English and Spanish are balanced at the smaller available pool; and
* every repeat uses one shuffled order per language, making its fractions
  strictly nested.

Subsets are constructed before detector loops, so all detector and n-gram
combinations see the exact same messages for a repeat/fraction pair.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import platform
import random
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from cogs.utils import language_benchmark as benchmark
from cogs.utils import language_benchmark_detectors as detector_adapters


DEFAULT_FRACTIONS: tuple[float, ...] = (0.1, 0.2, 0.4, 0.6, 0.8, 1.0)
DEFAULT_DETECTORS: tuple[str, ...] = ("sklearn_nb", "rai_current_nb")
DEFAULT_NGRAM_RANGES: tuple[tuple[int, int], ...] = ((2, 5),)
AGGREGATE_METRICS: tuple[str, ...] = (
    "examples",
    "correct",
    "abstentions",
    "accuracy",
    "macro_f1",
    "coverage",
    "covered_accuracy",
    "training_seconds",
    "prediction_seconds",
    "serialized_model_bytes",
)


@dataclass
class LearningCurveConfig:
    """Configuration for a complete learning-curve experiment."""

    cleaned_corpus: Path
    output_dir: Path
    raw_corpus: Path | None = None
    training_variant: str = "cleaned"
    training_view: str = "all"
    evaluation_view: str = "all"
    fractions: tuple[float, ...] = DEFAULT_FRACTIONS
    repeats: int = 5
    detectors: tuple[str, ...] = DEFAULT_DETECTORS
    ngram_ranges: tuple[tuple[int, int], ...] = DEFAULT_NGRAM_RANGES
    seed: int = 42
    evaluation_per_language: int = 1500


@dataclass(frozen=True)
class LearningPool:
    """Unique, non-conflicting candidates from which nested samples are drawn."""

    records: tuple[benchmark.CorpusRecord, ...]
    available_by_label: Mapping[str, int]
    dropped_for_balance_by_label: Mapping[str, int]
    balanced_per_language: int
    conflicting_group_count: int
    excluded_evaluation_group_count: int
    excluded_evaluation_occurrences: int
    source_occurrences: int
    training_min_chars: int
    digest: str


@dataclass(frozen=True)
class LearningSubset:
    """One balanced point on one repeat's nested learning curve."""

    repeat: int
    repeat_seed: int
    fraction: float
    per_language: int
    records: tuple[benchmark.CorpusRecord, ...]
    digest: str


@dataclass
class LearningCurveArtifacts:
    """In-memory results plus derived summaries written at checkpoints."""

    results: list[dict[str, Any]] = field(default_factory=list)
    aggregates: list[dict[str, Any]] = field(default_factory=list)
    fits: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def _validate_config(config: LearningCurveConfig) -> None:
    if config.training_view not in benchmark.VIEWS:
        raise ValueError(
            f"Unknown training view {config.training_view!r}; "
            f"choose from {sorted(benchmark.VIEWS)}"
        )
    if config.evaluation_view not in benchmark.VIEWS:
        raise ValueError(
            f"Unknown evaluation view {config.evaluation_view!r}; "
            f"choose from {sorted(benchmark.VIEWS)}"
        )
    if config.repeats < 1:
        raise ValueError("repeats must be at least 1")
    if config.evaluation_per_language < 1:
        raise ValueError("evaluation_per_language must be at least 1")
    if not config.detectors:
        raise ValueError("at least one detector is required")
    if not config.ngram_ranges:
        raise ValueError("at least one n-gram range is required")
    for minimum, maximum in config.ngram_ranges:
        if minimum < 1 or maximum < minimum:
            raise ValueError("n-gram ranges must satisfy 1 <= minimum <= maximum")
    _validated_fractions(config.fractions)


def _validated_fractions(fractions: Iterable[float]) -> tuple[float, ...]:
    values = tuple(float(value) for value in fractions)
    if not values:
        raise ValueError("at least one training fraction is required")
    if any(not math.isfinite(value) or value <= 0 or value > 1 for value in values):
        raise ValueError("training fractions must be finite and in (0, 1]")
    if any(left >= right for left, right in zip(values, values[1:])):
        raise ValueError("training fractions must be strictly increasing")
    return values


def _training_source(config: LearningCurveConfig) -> tuple[Path, int]:
    variants = {
        "cleaned": (config.cleaned_corpus, 0),
        "cleaned_min10": (config.cleaned_corpus, 10),
        "cleaned_min16": (config.cleaned_corpus, 16),
    }
    if config.training_variant == "raw":
        if config.raw_corpus is None:
            raise ValueError("training_variant='raw' requires raw_corpus")
        return config.raw_corpus, 0
    try:
        return variants[config.training_variant]
    except KeyError as exc:
        raise ValueError(
            "training_variant must be raw, cleaned, cleaned_min10, or "
            "cleaned_min16"
        ) from exc


def _record_sort_key(
    record: benchmark.CorpusRecord,
) -> tuple[str, int, str]:
    return record.source_file, record.source_line, record.text


def _records_digest(records: Iterable[benchmark.CorpusRecord]) -> str:
    rows = sorted(
        (record.label, record.normalized_text) for record in records
    )
    payload = "\n".join(f"{label}\t{text}" for label, text in rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_learning_pool(
    config: LearningCurveConfig,
    evaluation: benchmark.EvaluationSet,
) -> LearningPool:
    """Build unique, conflict-free candidates with no evaluation leakage."""

    corpus_dir, min_chars = _training_source(config)
    source_records = benchmark.load_corpus_records(
        corpus_dir,
        config.training_view,
        min_chars=min_chars,
    )
    grouped: dict[str, list[benchmark.CorpusRecord]] = defaultdict(list)
    for record in source_records:
        grouped[record.normalized_text].append(record)

    candidates: dict[str, list[benchmark.CorpusRecord]] = {
        "en": [],
        "es": [],
    }
    conflicting_groups = 0
    excluded_evaluation_groups = 0
    excluded_evaluation_occurrences = 0
    for normalized_text, group in grouped.items():
        labels = {record.label for record in group}
        if len(labels) != 1:
            conflicting_groups += 1
            continue
        if normalized_text in evaluation.normalized_keys:
            excluded_evaluation_groups += 1
            excluded_evaluation_occurrences += len(group)
            continue
        label = next(iter(labels))
        candidates[label].append(min(group, key=_record_sort_key))

    for rows in candidates.values():
        rows.sort(
            key=lambda record: (
                record.normalized_text,
                record.source_file,
                record.source_line,
            )
        )
    available = {label: len(candidates[label]) for label in ("en", "es")}
    balanced = min(available.values())
    if balanced < 1:
        raise ValueError(
            "learning pool needs at least one unique non-evaluation message "
            "in each language"
        )
    records = tuple(candidates["en"] + candidates["es"])
    return LearningPool(
        records=records,
        available_by_label=available,
        dropped_for_balance_by_label={
            label: available[label] - balanced
            for label in ("en", "es")
        },
        balanced_per_language=balanced,
        conflicting_group_count=conflicting_groups,
        excluded_evaluation_group_count=excluded_evaluation_groups,
        excluded_evaluation_occurrences=excluded_evaluation_occurrences,
        source_occurrences=len(source_records),
        training_min_chars=min_chars,
        digest=_records_digest(records),
    )


def make_nested_subsets(
    pool: LearningPool,
    *,
    fractions: Iterable[float] = DEFAULT_FRACTIONS,
    repeats: int = 5,
    seed: int = 42,
) -> list[LearningSubset]:
    """Create balanced, repeat-specific nested subsets.

    The larger language pool is reshuffled and truncated independently on each
    repeat.  This avoids permanently discarding the same excess candidates.
    """

    values = _validated_fractions(fractions)
    if repeats < 1:
        raise ValueError("repeats must be at least 1")

    by_label: dict[str, list[benchmark.CorpusRecord]] = {"en": [], "es": []}
    for record in pool.records:
        if record.label not in by_label:
            raise ValueError(f"unsupported pool label: {record.label!r}")
        by_label[record.label].append(record)
    if min(map(len, by_label.values())) < pool.balanced_per_language:
        raise ValueError("pool records do not match balanced_per_language")

    subsets: list[LearningSubset] = []
    for repeat in range(1, repeats + 1):
        repeat_seed = seed + repeat - 1
        orders: dict[str, list[benchmark.CorpusRecord]] = {}
        for label in ("en", "es"):
            rows = sorted(
                by_label[label],
                key=lambda record: (
                    record.normalized_text,
                    record.source_file,
                    record.source_line,
                ),
            )
            random.Random(f"{repeat_seed}:{label}").shuffle(rows)
            orders[label] = rows[: pool.balanced_per_language]

        for fraction in values:
            per_language = min(
                pool.balanced_per_language,
                max(1, math.ceil(pool.balanced_per_language * fraction)),
            )
            records = tuple(
                sorted(
                    orders["en"][:per_language]
                    + orders["es"][:per_language],
                    key=lambda record: (
                        record.label,
                        record.normalized_text,
                        record.source_file,
                        record.source_line,
                    ),
                )
            )
            subsets.append(
                LearningSubset(
                    repeat=repeat,
                    repeat_seed=repeat_seed,
                    fraction=fraction,
                    per_language=per_language,
                    records=records,
                    digest=_records_digest(records),
                )
            )
    return subsets


_T_CRITICAL_95: tuple[float, ...] = (
    math.inf,
    12.706,
    4.303,
    3.182,
    2.776,
    2.571,
    2.447,
    2.365,
    2.306,
    2.262,
    2.228,
    2.201,
    2.179,
    2.160,
    2.145,
    2.131,
    2.120,
    2.110,
    2.101,
    2.093,
    2.086,
    2.080,
    2.074,
    2.069,
    2.064,
    2.060,
    2.056,
    2.052,
    2.048,
    2.045,
    2.042,
)


def _t_critical_95(degrees_of_freedom: int) -> float:
    if degrees_of_freedom < 1:
        return math.inf
    if degrees_of_freedom < len(_T_CRITICAL_95):
        return _T_CRITICAL_95[degrees_of_freedom]
    # Cornish-Fisher expansion around z=.975. This is accurate enough for a
    # descriptive CI and avoids adding scipy solely for a critical value.
    z = 1.959963984540054
    degrees = float(degrees_of_freedom)
    return (
        z
        + (z**3 + z) / (4 * degrees)
        + (5 * z**5 + 16 * z**3 + 3 * z) / (96 * degrees**2)
        + (
            3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z
        )
        / (384 * degrees**3)
    )


def _sample_summary(
    values: Sequence[float],
    *,
    bounded: bool = False,
) -> dict[str, float | int]:
    mean = statistics.fmean(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0.0
    degrees_of_freedom = len(values) - 1
    critical = _t_critical_95(degrees_of_freedom)
    half_width = (
        critical * stdev / math.sqrt(len(values))
        if len(values) > 1
        else 0.0
    )
    low = mean - half_width
    high = mean + half_width
    if bounded:
        low = max(0.0, low)
        high = min(1.0, high)
    return {
        "mean": mean,
        "stdev": stdev,
        "ci95_low": low,
        "ci95_high": high,
        "n": len(values),
    }


def aggregate_learning_curve(
    results: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate repeat variation and add Student-t seed CIs."""

    group_fields = (
        "detector",
        "training_variant",
        "training_view",
        "evaluation_view",
        "ngram_min",
        "ngram_max",
        "fraction",
        "training_rows",
        "training_per_language",
        "length_bucket",
    )
    grouped: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in results:
        grouped[tuple(row.get(field) for field in group_fields)].append(row)

    aggregates: list[dict[str, Any]] = []
    for key, rows in grouped.items():
        aggregate = dict(zip(group_fields, key))
        aggregate["repeats_completed"] = len(rows)
        aggregate["subset_digests"] = sorted(
            str(row["subset_digest"])
            for row in rows
            if row.get("subset_digest")
        )
        for metric in AGGREGATE_METRICS:
            values = [
                float(row[metric])
                for row in rows
                if row.get(metric) is not None
            ]
            if not values:
                continue
            summary = _sample_summary(
                values,
                bounded=metric
                in {
                    "accuracy",
                    "macro_f1",
                    "coverage",
                    "covered_accuracy",
                },
            )
            for suffix, value in summary.items():
                aggregate[f"{metric}_{suffix}"] = value
        aggregates.append(aggregate)

    return sorted(
        aggregates,
        key=lambda row: (
            str(row.get("detector")),
            int(row.get("ngram_min") or 0),
            int(row.get("ngram_max") or 0),
            str(row.get("length_bucket")),
            float(row.get("fraction") or 0),
        ),
    )


def _power_solution(
    points: Sequence[tuple[float, float]],
    alpha: float,
) -> tuple[float, float, float]:
    """Least-squares floor/amplitude for a fixed exponent."""

    x_values = [training_rows ** (-alpha) for training_rows, _ in points]
    y_values = [error for _, error in points]
    x_mean = statistics.fmean(x_values)
    y_mean = statistics.fmean(y_values)
    denominator = sum((value - x_mean) ** 2 for value in x_values)
    if denominator <= 0:
        return 0.0, 0.0, math.inf

    amplitude = sum(
        (x_value - x_mean) * (y_value - y_mean)
        for x_value, y_value in zip(x_values, y_values)
    ) / denominator
    floor = y_mean - amplitude * x_mean

    # The learning-curve model requires non-negative asymptote and amplitude.
    if amplitude < 0:
        amplitude = 0.0
        floor = y_mean
    if floor < 0:
        floor = 0.0
        denominator_at_zero = sum(value * value for value in x_values)
        amplitude = (
            sum(value * error for value, error in zip(x_values, y_values))
            / denominator_at_zero
        )
    minimum_error = min(y_values)
    if floor > minimum_error:
        floor = minimum_error
        denominator_at_floor = sum(value * value for value in x_values)
        amplitude = max(
            0.0,
            sum(
                value * (error - floor)
                for value, error in zip(x_values, y_values)
            )
            / denominator_at_floor,
        )

    squared_error = sum(
        (
            error
            - (floor + amplitude * training_rows ** (-alpha))
        )
        ** 2
        for training_rows, error in points
    )
    return floor, amplitude, squared_error


def fit_power_law(
    points: Iterable[tuple[int | float, float]],
    *,
    projection_multipliers: Sequence[float] = (1.5, 2.0),
    projection_increments: Sequence[int] = (10_000,),
) -> dict[str, Any]:
    """Fit ``error(n) = floor + A * n**(-alpha)`` without extra packages."""

    grouped: dict[float, list[float]] = defaultdict(list)
    for training_rows, error in points:
        rows = float(training_rows)
        error_value = float(error)
        if (
            math.isfinite(rows)
            and rows > 0
            and math.isfinite(error_value)
            and 0 <= error_value <= 1
        ):
            grouped[rows].append(error_value)
    clean_points = sorted(
        (rows, statistics.fmean(errors))
        for rows, errors in grouped.items()
    )
    base: dict[str, Any] = {
        "status": "insufficient_data",
        "point_count": len(clean_points),
        "caveat": (
            "Power-law projections are extrapolations from in-domain samples, "
            "not guarantees about newly collected data."
        ),
    }
    if len(clean_points) < 4:
        return base

    # A dense one-dimensional grid is cheap for six-ish curve points. Refine
    # around its minimum so synthetic curves are recovered with useful
    # precision while avoiding scipy as a dependency.
    lower, upper = 0.01, 5.0
    best: tuple[float, float, float, float] | None = None
    for _ in range(6):
        steps = 240
        width = upper - lower
        for index in range(steps + 1):
            alpha = lower + width * index / steps
            floor, amplitude, squared_error = _power_solution(
                clean_points,
                alpha,
            )
            candidate = (squared_error, alpha, floor, amplitude)
            if best is None or candidate < best:
                best = candidate
        assert best is not None
        step = width / steps
        lower = max(0.001, best[1] - 2 * step)
        upper = min(10.0, best[1] + 2 * step)

    assert best is not None
    squared_error, alpha, floor, amplitude = best
    y_values = [error for _, error in clean_points]
    y_mean = statistics.fmean(y_values)
    total_squared_error = sum((value - y_mean) ** 2 for value in y_values)
    maximum_rows = max(rows for rows, _ in clean_points)
    r_squared = (
        1 - squared_error / total_squared_error
        if total_squared_error > 0
        else None
    )
    diagnostics: list[str] = []
    if alpha <= 0.011 or alpha >= 4.99:
        diagnostics.append("exponent reached the fit search boundary")
    if r_squared is None or r_squared < 0.5:
        diagnostics.append("fit explains less than half of observed variance")
    status = "ok"
    if amplitude <= 0:
        status = "no_decreasing_signal"
        diagnostics.append("observed errors have no decreasing power-law signal")
    elif diagnostics:
        status = "unstable"
    fit: dict[str, Any] = {
        **base,
        "status": status,
        "diagnostics": diagnostics,
        "floor": floor,
        "amplitude": amplitude,
        "alpha": alpha,
        "rmse": math.sqrt(squared_error / len(clean_points)),
        "r_squared": r_squared,
        "maximum_observed_training_rows": int(maximum_rows),
        "observed_error_at_maximum": clean_points[-1][1],
    }
    projections: dict[str, dict[str, float | int]] = {}
    for multiplier in projection_multipliers:
        multiplier_value = float(multiplier)
        if not math.isfinite(multiplier_value) or multiplier_value <= 1:
            raise ValueError("projection multipliers must be finite and > 1")
        projected_rows = maximum_rows * multiplier_value
        projected_error = floor + amplitude * projected_rows ** (-alpha)
        projections[f"{multiplier_value:g}x"] = {
            "training_rows": int(round(projected_rows)),
            "error": projected_error,
            "accuracy": 1 - projected_error,
            "accuracy_gain_from_observed": (
                clean_points[-1][1] - projected_error
            ),
        }
    for increment in projection_increments:
        increment_value = int(increment)
        if increment_value <= 0:
            raise ValueError("projection increments must be positive integers")
        projected_rows = maximum_rows + increment_value
        projected_error = floor + amplitude * projected_rows ** (-alpha)
        projections[f"+{increment_value}"] = {
            "training_rows": int(round(projected_rows)),
            "error": projected_error,
            "accuracy": 1 - projected_error,
            "accuracy_gain_from_observed": (
                clean_points[-1][1] - projected_error
            ),
        }
    fit["projections"] = projections
    return fit


def _fits_from_aggregates(
    aggregates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    group_fields = (
        "detector",
        "training_variant",
        "training_view",
        "evaluation_view",
        "ngram_min",
        "ngram_max",
        "length_bucket",
    )
    grouped: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in aggregates:
        if row.get("accuracy_mean") is None:
            continue
        grouped[tuple(row.get(field) for field in group_fields)].append(row)

    fits: list[dict[str, Any]] = []
    for key, rows in grouped.items():
        fit = fit_power_law(
            (
                int(row["training_rows"]),
                1 - float(row["accuracy_mean"]),
            )
            for row in rows
        )
        endpoint = max(rows, key=lambda row: int(row["training_rows"]))
        examples = endpoint.get("examples_mean")
        correct = endpoint.get("correct_mean")
        if examples is not None and correct is not None:
            endpoint_errors = float(examples) - float(correct)
            fit["endpoint_error_count_mean"] = endpoint_errors
            if endpoint_errors < 20:
                diagnostic = (
                    "maximum-size evaluation has fewer than 20 mean errors"
                )
                fit.setdefault("diagnostics", []).append(diagnostic)
                if fit.get("status") == "ok":
                    fit["status"] = "unstable"
        fit.update(dict(zip(group_fields, key)))
        fits.append(fit)
    return sorted(
        fits,
        key=lambda row: (
            str(row.get("detector")),
            int(row.get("ngram_min") or 0),
            int(row.get("ngram_max") or 0),
            str(row.get("length_bucket")),
        ),
    )


def _metric_rows(
    base: Mapping[str, Any],
    evaluation: benchmark.EvaluationSet,
    predictions: Sequence[str],
) -> list[dict[str, Any]]:
    indexes_by_bucket = {
        "all": list(range(len(evaluation.records))),
        "16+": [
            index
            for index, record in enumerate(evaluation.records)
            if record.characters >= 16
        ],
    }
    rows: list[dict[str, Any]] = []
    for bucket, indexes in indexes_by_bucket.items():
        if not indexes:
            continue
        truth = [evaluation.records[index].label for index in indexes]
        predicted = [predictions[index] for index in indexes]
        row = dict(base)
        row["length_bucket"] = bucket
        row.update(benchmark.classification_metrics(truth, predicted))
        rows.append(row)
    return rows


def _serialized_size(detector: Any) -> int | None:
    method = getattr(detector, "serialized_size_bytes", None)
    if not callable(method):
        return None
    try:
        return int(method())
    except Exception:
        return None


def _evaluation_metadata(
    evaluation: benchmark.EvaluationSet,
) -> dict[str, Any]:
    return {
        "view": evaluation.view,
        "records": len(evaluation.records),
        "selected_by_label": dict(evaluation.selected_by_label),
        "available_unique_by_label": dict(
            evaluation.available_unique_by_label
        ),
        "conflicting_group_count": evaluation.conflicting_group_count,
        "digest": evaluation.digest,
    }


def _pool_metadata(pool: LearningPool) -> dict[str, Any]:
    return {
        "available_by_label": dict(pool.available_by_label),
        "dropped_for_balance_by_label": dict(
            pool.dropped_for_balance_by_label
        ),
        "balanced_per_language": pool.balanced_per_language,
        "conflicting_group_count": pool.conflicting_group_count,
        "excluded_evaluation_group_count": pool.excluded_evaluation_group_count,
        "excluded_evaluation_occurrences": pool.excluded_evaluation_occurrences,
        "source_occurrences": pool.source_occurrences,
        "training_min_chars": pool.training_min_chars,
        "digest": pool.digest,
    }


def run_learning_curve(
    config: LearningCurveConfig,
) -> LearningCurveArtifacts:
    """Run and checkpoint a complete local learning-curve experiment."""

    _validate_config(config)
    if not config.cleaned_corpus.is_dir():
        raise FileNotFoundError(
            f"Cleaned corpus directory does not exist: {config.cleaned_corpus}"
        )
    training_dir, _ = _training_source(config)
    if not training_dir.is_dir():
        raise FileNotFoundError(
            f"Training corpus directory does not exist: {training_dir}"
        )

    evaluation = benchmark.build_evaluation_set(
        config.cleaned_corpus,
        config.evaluation_view,
        seed=config.seed,
        per_language=config.evaluation_per_language,
    )
    pool = build_learning_pool(config, evaluation)
    subsets = make_nested_subsets(
        pool,
        fractions=config.fractions,
        repeats=config.repeats,
        seed=config.seed,
    )
    artifacts = LearningCurveArtifacts(
        metadata={
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "python_version": sys.version,
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "methodology": "balanced_unique_normalized_nested_subsets",
            "detector_seed": config.seed,
            "sampling_seed_rule": "config.seed + repeat - 1",
            "training_source": str(training_dir.resolve()),
            "training_source_hashes": benchmark.corpus_hashes(training_dir),
            "cleaned_corpus": str(config.cleaned_corpus.resolve()),
            "cleaned_corpus_hashes": benchmark.corpus_hashes(
                config.cleaned_corpus
            ),
            "detector_inventory": detector_adapters.detector_specs(),
            "evaluation": _evaluation_metadata(evaluation),
            "pool": _pool_metadata(pool),
            "subset_count": len(subsets),
            "subsets": [
                {
                    "repeat": subset.repeat,
                    "repeat_seed": subset.repeat_seed,
                    "detector_seed": config.seed,
                    "fraction": subset.fraction,
                    "training_per_language": subset.per_language,
                    "training_rows": len(subset.records),
                    "digest": subset.digest,
                }
                for subset in subsets
            ],
        }
    )
    save_learning_curve_artifacts(config, artifacts)

    for subset in subsets:
        texts = [record.text for record in subset.records]
        labels = [record.label for record in subset.records]
        for detector_name in config.detectors:
            for ngram_range in config.ngram_ranges:
                run_identity = {
                    "detector": detector_name,
                    "training_variant": config.training_variant,
                    "training_view": config.training_view,
                    "evaluation_view": config.evaluation_view,
                    "ngram_min": ngram_range[0],
                    "ngram_max": ngram_range[1],
                    "repeat": subset.repeat,
                    "repeat_seed": subset.repeat_seed,
                    "fraction": subset.fraction,
                    "training_rows": len(subset.records),
                    "training_per_language": subset.per_language,
                    "training_english": subset.per_language,
                    "training_spanish": subset.per_language,
                    "subset_digest": subset.digest,
                    "evaluation_digest": evaluation.digest,
                }
                print(
                    "[learning-curve] "
                    f"{detector_name} ngram={ngram_range} "
                    f"repeat={subset.repeat} fraction={subset.fraction:g} "
                    f"rows={len(subset.records)}",
                    flush=True,
                )
                try:
                    detector = detector_adapters.create_detector(
                        detector_name,
                        ngram_range=ngram_range,
                        # Hold model randomness fixed so repeat dispersion
                        # isolates training-subset sampling variance.
                        seed=config.seed,
                    )
                    initialize_start = time.perf_counter()
                    detector.initialize()
                    initialization_seconds = (
                        time.perf_counter() - initialize_start
                    )
                    fit_start = time.perf_counter()
                    detector.fit(texts, labels)
                    training_seconds = time.perf_counter() - fit_start
                    predict_start = time.perf_counter()
                    predictions = list(
                        detector.predict(
                            [record.text for record in evaluation.records]
                        )
                    )
                    prediction_seconds = time.perf_counter() - predict_start
                    if len(predictions) != len(evaluation.records):
                        raise ValueError(
                            f"detector returned {len(predictions)} predictions "
                            f"for {len(evaluation.records)} evaluation records"
                        )
                    base = {
                        **run_identity,
                        "initialization_seconds": initialization_seconds,
                        "training_seconds": training_seconds,
                        "prediction_seconds": prediction_seconds,
                        "serialized_model_bytes": _serialized_size(detector),
                    }
                    artifacts.results.extend(
                        _metric_rows(base, evaluation, predictions)
                    )
                except Exception as exc:
                    artifacts.skipped.append(
                        {
                            **run_identity,
                            "reason": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    print(
                        f"  skipped: {type(exc).__name__}: {exc}",
                        flush=True,
                    )
                finally:
                    save_learning_curve_artifacts(config, artifacts)

    # The final save is intentional: it refreshes aggregates/fits even if the
    # last attempted detector was skipped.
    save_learning_curve_artifacts(config, artifacts)
    return artifacts


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


def _csv_text(rows: Sequence[Mapping[str, Any]]) -> str:
    keys = sorted({key for row in rows for key in row})
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=keys,
        # Keep checkpoint CSVs byte-identical and readable across Windows and
        # POSIX instead of letting two newline translators produce CRCRLF.
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list, tuple))
                else value
                for key, value in row.items()
            }
        )
    return output.getvalue()


def _atomic_write_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def save_learning_curve_artifacts(
    config: LearningCurveConfig,
    artifacts: LearningCurveArtifacts,
) -> None:
    """Checkpoint raw runs, aggregates, fitted curves, and a report."""

    config.output_dir.mkdir(parents=True, exist_ok=True)
    artifacts.aggregates = aggregate_learning_curve(artifacts.results)
    artifacts.fits = _fits_from_aggregates(artifacts.aggregates)
    payload = {
        "metadata": artifacts.metadata,
        "config": _json_safe(asdict(config)),
        "results": artifacts.results,
        "aggregates": artifacts.aggregates,
        "fits": artifacts.fits,
        "skipped": artifacts.skipped,
    }
    _atomic_write_text(
        config.output_dir / "results.csv",
        _csv_text(artifacts.results),
    )
    _atomic_write_text(
        config.output_dir / "aggregates.csv",
        _csv_text(artifacts.aggregates),
    )
    _atomic_write_text(
        config.output_dir / "fits.csv",
        _csv_text(artifacts.fits),
    )
    _atomic_write_text(
        config.output_dir / "results.json",
        json.dumps(payload, ensure_ascii=False, indent=2),
    )
    _atomic_write_text(
        config.output_dir / "report.md",
        render_learning_curve_report(artifacts),
    )


def _percent(value: Any) -> str:
    return "—" if value is None else f"{100 * float(value):.3f}%"


def _gain_text(value: Any) -> str:
    if value is None:
        return "—"
    return f"{100 * float(value):+.3f} pp"


def _projection_text(projection: Mapping[str, Any]) -> str:
    accuracy = projection.get("accuracy")
    gain = projection.get("accuracy_gain_from_observed")
    if accuracy is None:
        return "—"
    return f"{_percent(accuracy)} ({_gain_text(gain)})"


def _ci_text(row: Mapping[str, Any], metric: str) -> str:
    mean = row.get(f"{metric}_mean")
    low = row.get(f"{metric}_ci95_low")
    high = row.get(f"{metric}_ci95_high")
    if mean is None:
        return "—"
    if low is None or high is None:
        return _percent(mean)
    return f"{_percent(mean)} [{_percent(low)}, {_percent(high)}]"


def _append_aggregate_table(
    lines: list[str],
    *,
    title: str,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    lines.extend(
        [
            f"## {title}",
            "",
            "| Detector | N-grams | Fraction | Rows | "
            "Accuracy mean [95% seed CI] | Macro F1 mean [95% seed CI] | "
            "Fit seconds mean | Model MiB mean |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        model_bytes = row.get("serialized_model_bytes_mean")
        model_mib = (
            "—"
            if model_bytes is None
            else f"{float(model_bytes) / (1024 * 1024):.2f}"
        )
        training_seconds = row.get("training_seconds_mean")
        lines.append(
            f"| {row.get('detector')} | "
            f"({row.get('ngram_min')},{row.get('ngram_max')}) | "
            f"{float(row.get('fraction') or 0):.0%} | "
            f"{row.get('training_rows')} | "
            f"{_ci_text(row, 'accuracy')} | "
            f"{_ci_text(row, 'macro_f1')} | "
            f"{'—' if training_seconds is None else f'{float(training_seconds):.3f}'} | "
            f"{model_mib} |"
        )
    if not rows:
        lines.append(
            "| — | — | — | — | No completed runs | — | — | — |"
        )
    lines.append("")


def _append_projection_table(
    lines: list[str],
    *,
    title: str,
    fits: Sequence[Mapping[str, Any]],
) -> None:
    lines.extend(
        [
            f"## {title}",
            "",
            "Fits use `error(n) = floor + A × n^-alpha`. Projections assume "
            "that future clean messages resemble the present training "
            "distribution; targeted or shifted data can behave very "
            "differently.",
            "",
            "| Detector | N-grams | Status | Error floor | Alpha | R² | "
            "Projected accuracy at +10,000 (gain) | "
            "Projected accuracy at 1.5× (gain) | "
            "Projected accuracy at 2× (gain) |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for fit in fits:
        projections = fit.get("projections", {})
        plus_ten_thousand = projections.get("+10000", {})
        one_and_half = projections.get("1.5x", {})
        double = projections.get("2x", {})
        r_squared = fit.get("r_squared")
        alpha = fit.get("alpha")
        alpha_text = "—" if alpha is None else f"{float(alpha):.3f}"
        lines.append(
            f"| {fit.get('detector')} | "
            f"({fit.get('ngram_min')},{fit.get('ngram_max')}) | "
            f"{fit.get('status')} | {_percent(fit.get('floor'))} | "
            f"{alpha_text} | "
            f"{'—' if r_squared is None else f'{float(r_squared):.3f}'} | "
            f"{_projection_text(plus_ten_thousand)} | "
            f"{_projection_text(one_and_half)} | "
            f"{_projection_text(double)} |"
        )
    if not fits:
        lines.append(
            "| — | — | insufficient_data | — | — | — | — | — | — |"
        )
    diagnostics = [
        (
            f"- `{fit.get('detector')}`: "
            + "; ".join(str(item) for item in fit.get("diagnostics", []))
        )
        for fit in fits
        if fit.get("diagnostics")
    ]
    if diagnostics:
        lines.extend(["", "Fit diagnostics:", "", *diagnostics])
    lines.append("")


def render_learning_curve_report(
    artifacts: LearningCurveArtifacts,
) -> str:
    """Render a compact, self-contained Markdown interpretation aid."""

    evaluation = artifacts.metadata.get("evaluation", {})
    pool = artifacts.metadata.get("pool", {})
    balanced_per_language = pool.get("balanced_per_language")
    balanced_endpoint = (
        2 * int(balanced_per_language)
        if balanced_per_language is not None
        else None
    )
    endpoint_comparison = (
        "For the current audited corpus, that is **53,216 balanced unique "
        "representatives**, not the production-parity model's **70,780 "
        "duplicated rows**."
        if balanced_endpoint == 53_216
        else (
            f"This run's endpoint is **{balanced_endpoint:,} balanced unique "
            "representatives**, not a duplicated all-row production endpoint."
            if balanced_endpoint is not None
            else "This run did not record a balanced endpoint."
        )
    )
    all_rows = [
        row
        for row in artifacts.aggregates
        if row.get("length_bucket") == "all"
    ]
    production_rows = [
        row
        for row in artifacts.aggregates
        if row.get("length_bucket") == "16+"
    ]
    all_fits = [
        fit
        for fit in artifacts.fits
        if fit.get("length_bucket") == "all"
    ]
    production_fits = [
        fit
        for fit in artifacts.fits
        if fit.get("length_bucket") == "16+"
    ]
    lines = [
        "# Rai language detector learning curve",
        "",
        "This experiment ran locally and offline. It does not call paid or "
        "network-backed services.",
        "",
        "## Method",
        "",
        "The fixed evaluation set contains one representative per normalized "
        "message and is excluded in full from training. Training candidates "
        "are also normalized-text groups: conflicting labels are discarded, "
        "one deterministic representative is retained, English and Spanish "
        "are balanced, and every repeat uses nested subsets.",
        "",
        "The 100% point is therefore the balanced unique-message endpoint. "
        "It is not the production model's duplicated all-row training endpoint.",
        "",
        endpoint_comparison,
        "",
        f"- Evaluation records: {evaluation.get('records', '—')}",
        f"- Evaluation digest: `{evaluation.get('digest', '—')}`",
        f"- Unique training candidates: {pool.get('available_by_label', '—')}",
        f"- Balanced maximum per language: {pool.get('balanced_per_language', '—')}",
        f"- 100% balanced unique-message endpoint: {balanced_endpoint or '—'} rows",
        f"- Unique groups omitted for balance: {pool.get('dropped_for_balance_by_label', '—')}",
        f"- Conflicting training groups excluded: {pool.get('conflicting_group_count', '—')}",
        f"- Evaluation groups excluded from training: {pool.get('excluded_evaluation_group_count', '—')}",
        "",
        "The intervals below are Student-t 95% confidence intervals over "
        "sampling seeds (and are clipped to [0,1] for proportion metrics). "
        "They are conditional on this one fixed holdout. With only a few "
        "repeats they describe repeat "
        "variation imprecisely and are not population-level guarantees.",
        "",
    ]
    _append_aggregate_table(
        lines,
        title="All-message results",
        rows=all_rows,
    )
    _append_projection_table(
        lines,
        title="All-message power-law projections",
        fits=all_fits,
    )
    _append_aggregate_table(
        lines,
        title="Production-length results (16+ characters)",
        rows=production_rows,
    )
    _append_projection_table(
        lines,
        title="Production-length power-law projections",
        fits=production_fits,
    )
    lines.extend(
        [
            "## Caveats",
            "",
            "- A plateau on this in-domain corpus does not prove that new dialect, "
            "slang, code-switch, or adversarial examples would be unhelpful.",
            "- The evaluation labels still come from the cleaned chat-corpus family, "
            "not an independently adjudicated external gold set.",
            "- Power-law parameters can be unstable when errors are rare or the "
            "observed curve is flat/non-monotonic. Treat projected differences of "
            "a few messages as indistinguishable.",
            "- Fraction comparisons are paired by repeat because their subsets are "
            "nested; overlapping or non-overlapping marginal intervals alone do "
            "not establish a significant difference.",
            "",
            f"Completed metric rows: {len(artifacts.results)}. "
            f"Skipped runs: {len(artifacts.skipped)}.",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "DEFAULT_DETECTORS",
    "DEFAULT_FRACTIONS",
    "DEFAULT_NGRAM_RANGES",
    "LearningCurveArtifacts",
    "LearningCurveConfig",
    "LearningPool",
    "LearningSubset",
    "aggregate_learning_curve",
    "build_learning_pool",
    "fit_power_law",
    "make_nested_subsets",
    "render_learning_curve_report",
    "run_learning_curve",
    "save_learning_curve_artifacts",
]
