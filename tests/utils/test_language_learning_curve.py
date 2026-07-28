from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

import pytest

from cogs.utils import language_benchmark as benchmark
from cogs.utils import language_learning_curve as learning


def write_corpus(
    directory: Path,
    rows_by_file: dict[str, tuple[str, ...]],
) -> Path:
    directory.mkdir()
    for filename in benchmark.CORPUS_LABELS:
        with (directory / filename).open(
            "w",
            encoding="utf-8",
            newline="",
        ) as target:
            writer = csv.writer(
                target,
                delimiter=" ",
                quotechar="|",
                lineterminator="\r\n",
            )
            for index, text in enumerate(rows_by_file.get(filename, ()), 1):
                writer.writerow((index, 1, text))
    return directory


def evaluation_with_keys(*keys: str) -> benchmark.EvaluationSet:
    return benchmark.EvaluationSet(
        view="all",
        records=(),
        normalized_keys=frozenset(keys),
        conflicting_group_count=0,
        available_unique_by_label={"en": 0, "es": 0},
        selected_by_label={"en": 0, "es": 0},
        digest="test-evaluation",
    )


def config_for(
    tmp_path: Path,
    corpus: Path,
    **overrides,
) -> learning.LearningCurveConfig:
    values = {
        "cleaned_corpus": corpus,
        "output_dir": tmp_path / "output",
        "evaluation_per_language": 1,
        "fractions": (0.5, 1.0),
        "repeats": 2,
        "detectors": ("fake_a", "fake_b"),
        "ngram_ranges": ((2, 5),),
    }
    values.update(overrides)
    return learning.LearningCurveConfig(**values)


def test_build_pool_excludes_conflicts_eval_and_duplicate_occurrences(
    tmp_path: Path,
):
    corpus = write_corpus(
        tmp_path / "corpus",
        {
            "advanced.csv": (
                "Evaluation English",
                "  Duplicate   English ",
                "Cross label",
                "English extra one",
                "English extra two",
            ),
            "beginner.csv": ("duplicate english",),
            "avanzado.csv": (
                "Evaluation Spanish",
                "cross   label",
                "Mensaje español uno",
            ),
            "principiante.csv": (
                "mensaje español uno",
                "Mensaje español dos",
            ),
        },
    )
    config = config_for(tmp_path, corpus)

    pool = learning.build_learning_pool(
        config,
        evaluation_with_keys("evaluation english", "evaluation spanish"),
    )

    keys = {record.normalized_text for record in pool.records}
    assert keys == {
        "duplicate english",
        "english extra one",
        "english extra two",
        "mensaje español uno",
        "mensaje español dos",
    }
    assert "cross label" not in keys
    assert pool.available_by_label == {"en": 3, "es": 2}
    assert pool.balanced_per_language == 2
    assert pool.dropped_for_balance_by_label == {"en": 1, "es": 0}
    assert pool.conflicting_group_count == 1
    assert pool.excluded_evaluation_group_count == 2
    assert pool.excluded_evaluation_occurrences == 2

    duplicate = next(
        record
        for record in pool.records
        if record.normalized_text == "duplicate english"
    )
    assert (duplicate.source_file, duplicate.source_line) == (
        "advanced.csv",
        2,
    )
    assert keys.isdisjoint({"evaluation english", "evaluation spanish"})


def test_nested_subsets_are_balanced_nested_and_deterministic(tmp_path: Path):
    corpus = write_corpus(
        tmp_path / "corpus",
        {
            "advanced.csv": tuple(
                f"English unique message number {index}" for index in range(12)
            ),
            "avanzado.csv": tuple(
                f"Mensaje único español número {index}" for index in range(10)
            ),
        },
    )
    pool = learning.build_learning_pool(
        config_for(tmp_path, corpus),
        evaluation_with_keys(),
    )

    first = learning.make_nested_subsets(
        pool,
        fractions=(0.1, 0.3, 0.6, 1.0),
        repeats=3,
        seed=77,
    )
    second = learning.make_nested_subsets(
        pool,
        fractions=(0.1, 0.3, 0.6, 1.0),
        repeats=3,
        seed=77,
    )

    assert first == second
    by_repeat: dict[int, list[learning.LearningSubset]] = defaultdict(list)
    for subset in first:
        by_repeat[subset.repeat].append(subset)
        counts = {
            label: sum(record.label == label for record in subset.records)
            for label in ("en", "es")
        }
        assert counts == {
            "en": subset.per_language,
            "es": subset.per_language,
        }
        assert subset.digest == learning._records_digest(subset.records)

    for subsets in by_repeat.values():
        prior_keys: set[tuple[str, str]] = set()
        for subset in subsets:
            keys = {
                (record.label, record.normalized_text)
                for record in subset.records
            }
            assert prior_keys <= keys
            prior_keys = keys
        assert subsets[-1].per_language == 10

    # Different repeats generally sample different prefixes and different
    # excess-English groups, while preserving exact nesting within a repeat.
    assert len({subsets[1].digest for subsets in by_repeat.values()}) > 1


def test_aggregate_reports_mean_stdev_and_seed_ci():
    base = {
        "detector": "fake",
        "training_variant": "cleaned",
        "training_view": "all",
        "evaluation_view": "all",
        "ngram_min": 2,
        "ngram_max": 5,
        "fraction": 0.5,
        "training_rows": 100,
        "training_per_language": 50,
        "length_bucket": "16+",
    }
    rows = [
        {
            **base,
            "repeat": 1,
            "subset_digest": "one",
            "accuracy": 0.8,
            "macro_f1": 0.79,
            "training_seconds": 2.0,
        },
        {
            **base,
            "repeat": 2,
            "subset_digest": "two",
            "accuracy": 1.0,
            "macro_f1": 0.99,
            "training_seconds": 4.0,
        },
    ]

    aggregate = learning.aggregate_learning_curve(rows)[0]

    assert aggregate["accuracy_mean"] == pytest.approx(0.9)
    assert aggregate["accuracy_stdev"] == pytest.approx(math.sqrt(0.02))
    half_width = 12.706 * math.sqrt(0.02) / math.sqrt(2)
    assert half_width > 0.9
    assert aggregate["accuracy_ci95_low"] == 0.0
    assert aggregate["accuracy_ci95_high"] == 1.0
    assert aggregate["accuracy_n"] == 2
    assert aggregate["training_seconds_mean"] == 3.0
    assert aggregate["repeats_completed"] == 2
    assert aggregate["subset_digests"] == ["one", "two"]


def test_power_law_fit_recovers_synthetic_curve_and_projects():
    floor = 0.02
    amplitude = 0.8
    alpha = 0.6
    points = [
        (rows, floor + amplitude * rows ** (-alpha))
        for rows in (100, 200, 400, 800, 1600, 3200)
    ]

    fit = learning.fit_power_law(points)

    assert fit["status"] == "ok"
    assert fit["floor"] == pytest.approx(floor, abs=2e-6)
    assert fit["amplitude"] == pytest.approx(amplitude, rel=2e-4)
    assert fit["alpha"] == pytest.approx(alpha, rel=2e-4)
    assert fit["rmse"] < 1e-8
    assert fit["r_squared"] > 0.999999
    expected_double_error = floor + amplitude * 6400 ** (-alpha)
    assert fit["projections"]["2x"]["error"] == pytest.approx(
        expected_double_error,
        rel=2e-4,
    )
    expected_plus_ten_thousand = (
        floor + amplitude * 13_200 ** (-alpha)
    )
    assert fit["projections"]["+10000"]["error"] == pytest.approx(
        expected_plus_ten_thousand,
        rel=2e-4,
    )
    assert fit["projections"]["+10000"][
        "accuracy_gain_from_observed"
    ] == pytest.approx(
        points[-1][1] - expected_plus_ten_thousand,
        rel=2e-4,
    )

    insufficient = learning.fit_power_law([(10, 0.2), (20, 0.1)])
    assert insufficient["status"] == "insufficient_data"


def test_small_end_to_end_shares_subsets_and_checkpoints(
    tmp_path: Path,
    monkeypatch,
):
    corpus = write_corpus(
        tmp_path / "corpus",
        {
            "advanced.csv": tuple(
                f"English training sentence number {index} is definitely long"
                for index in range(6)
            ),
            "beginner.csv": tuple(
                f"English beginner sentence number {index} remains quite long"
                for index in range(2)
            ),
            "avanzado.csv": tuple(
                f"Mensaje español de entrenamiento número {index} es muy largo"
                for index in range(6)
            ),
            "principiante.csv": tuple(
                f"Mensaje español principiante número {index} sigue muy largo"
                for index in range(2)
            ),
        },
    )
    config = config_for(tmp_path, corpus)
    created_seeds: list[int] = []

    class FakeDetector:
        def initialize(self):
            return self

        def fit(self, texts, labels):
            assert len(texts) == len(labels)
            assert set(labels) == {"en", "es"}
            return self

        def predict(self, texts):
            return [
                "en" if text.casefold().startswith("english") else "es"
                for text in texts
            ]

        @staticmethod
        def serialized_size_bytes():
            return 123

    def create_detector(name, ngram_range, seed):
        assert name in {"fake_a", "fake_b"}
        assert ngram_range == (2, 5)
        created_seeds.append(seed)
        return FakeDetector()

    monkeypatch.setattr(
        learning.detector_adapters,
        "create_detector",
        create_detector,
    )
    original_save = learning.save_learning_curve_artifacts
    save_calls = 0

    def counting_save(config, artifacts):
        nonlocal save_calls
        save_calls += 1
        original_save(config, artifacts)

    monkeypatch.setattr(
        learning,
        "save_learning_curve_artifacts",
        counting_save,
    )

    artifacts = learning.run_learning_curve(config)

    # 2 fractions x 2 repeats x 2 detectors x (all and 16+) metric rows.
    assert len(artifacts.results) == 16
    assert not artifacts.skipped
    assert save_calls == 10  # initial + 8 completed runs + final
    assert set(created_seeds) == {config.seed}
    assert len(artifacts.aggregates) == 8
    assert len(artifacts.fits) == 4

    # Both detectors receive the exact same subset for each curve point.
    grouped: dict[tuple[int, float], set[str]] = defaultdict(set)
    for row in artifacts.results:
        if row["length_bucket"] == "all":
            grouped[(row["repeat"], row["fraction"])].add(
                row["subset_digest"]
            )
            assert row["accuracy"] == 1.0
            assert row["serialized_model_bytes"] == 123
    assert all(len(digests) == 1 for digests in grouped.values())

    output_files = {
        path.name for path in config.output_dir.iterdir() if path.is_file()
    }
    assert output_files == {
        "aggregates.csv",
        "fits.csv",
        "report.md",
        "results.csv",
        "results.json",
    }
    for filename in ("aggregates.csv", "fits.csv", "results.csv"):
        assert b"\r" not in (config.output_dir / filename).read_bytes()
    report = (config.output_dir / "report.md").read_text(encoding="utf-8")
    assert "locally and offline" in report
    assert "balanced unique-message endpoint" in report
    assert "## All-message results" in report
    assert "## Production-length results" in report
    assert "## All-message power-law projections" in report
    assert "## Production-length power-law projections" in report


@pytest.mark.parametrize(
    "fractions",
    (
        (),
        (0.0, 1.0),
        (0.5, 0.4),
        (0.5, 0.5),
        (0.5, 1.1),
    ),
)
def test_nested_subset_rejects_invalid_fractions(
    tmp_path: Path,
    fractions,
):
    corpus = write_corpus(
        tmp_path / "corpus",
        {
            "advanced.csv": ("English message",),
            "avanzado.csv": ("Mensaje español",),
        },
    )
    pool = learning.build_learning_pool(
        config_for(tmp_path, corpus),
        evaluation_with_keys(),
    )
    with pytest.raises(ValueError):
        learning.make_nested_subsets(pool, fractions=fractions)
