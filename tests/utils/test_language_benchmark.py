from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from cogs.utils import language_benchmark as benchmark


EMPTY_CORPUS = {
    filename: ()
    for filename in benchmark.CORPUS_LABELS
}


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


def config_for(
    tmp_path: Path,
    *,
    raw_corpus: Path,
    cleaned_corpus: Path,
) -> benchmark.BenchmarkConfig:
    return benchmark.BenchmarkConfig(
        raw_corpus=raw_corpus,
        cleaned_corpus=cleaned_corpus,
        output_dir=tmp_path / "output",
        package_detectors=(),
    )


def empty_evaluation() -> benchmark.EvaluationSet:
    return benchmark.EvaluationSet(
        view="all",
        records=(),
        normalized_keys=frozenset(),
        conflicting_group_count=0,
        available_unique_by_label={"en": 0, "es": 0},
        selected_by_label={"en": 0, "es": 0},
        digest="empty",
    )


def record(text: str, label: str, line: int) -> benchmark.CorpusRecord:
    return benchmark.CorpusRecord(
        source_file="advanced.csv" if label == "en" else "avanzado.csv",
        source_line=line,
        text=text,
        label=label,
        normalized_text=benchmark.normalize_text(text),
    )


def test_grouped_evaluation_normalizes_duplicates_and_excludes_conflicts(
    tmp_path: Path,
):
    cleaned_rows = {
        "advanced.csv": (
            "  ＨＥＬＬＯ   WORLD  ",
            "Cross Label Text",
            "English unique advanced",
        ),
        "beginner.csv": (
            "hello world",
            "English unique beginner",
        ),
        "avanzado.csv": (
            "cross   label text",
            "  HOLA   MUNDO  ",
            "Mensaje único avanzado",
        ),
        "principiante.csv": (
            "hola mundo",
            "Mensaje único principiante",
        ),
    }
    cleaned = write_corpus(tmp_path / "cleaned", cleaned_rows)

    evaluation = benchmark.build_evaluation_set(
        cleaned,
        "all",
        seed=42,
        per_language=100,
    )

    assert benchmark.normalize_text("  ＨＥＬＬＯ \t WORLD\n") == "hello world"
    assert evaluation.conflicting_group_count == 1
    assert evaluation.available_unique_by_label == {"en": 3, "es": 3}
    assert evaluation.selected_by_label == {"en": 3, "es": 3}
    assert len(evaluation.records) == 6
    assert len(evaluation.normalized_keys) == 6
    assert "cross label text" not in evaluation.normalized_keys
    assert Counter(row.normalized_text for row in evaluation.records) == Counter(
        {
            "hello world": 1,
            "english unique advanced": 1,
            "english unique beginner": 1,
            "hola mundo": 1,
            "mensaje único avanzado": 1,
            "mensaje único principiante": 1,
        }
    )

    # A same-label duplicate contributes only its deterministic first representative.
    hello = next(
        row for row in evaluation.records if row.normalized_text == "hello world"
    )
    assert (hello.source_file, hello.source_line) == ("advanced.csv", 1)

    repeated = benchmark.build_evaluation_set(
        cleaned,
        "all",
        seed=42,
        per_language=100,
    )
    assert repeated.records == evaluation.records
    assert repeated.digest == evaluation.digest


def test_training_excludes_every_occurrence_of_evaluation_texts(
    tmp_path: Path,
):
    cleaned_rows = {
        "advanced.csv": (
            "  ＨＥＬＬＯ   WORLD  ",
            "Cross Label Text",
            "English unique advanced",
        ),
        "beginner.csv": (
            "hello world",
            "English unique beginner",
        ),
        "avanzado.csv": (
            "cross   label text",
            "  HOLA   MUNDO  ",
            "Mensaje único avanzado",
        ),
        "principiante.csv": (
            "hola mundo",
            "Mensaje único principiante",
        ),
    }
    raw_rows = {
        **cleaned_rows,
        "advanced.csv": (
            *cleaned_rows["advanced.csv"],
            "HELLO WORLD",
            "Raw-only English keeper",
        ),
        "avanzado.csv": (
            *cleaned_rows["avanzado.csv"],
            "Hola Mundo",
            "Mensaje español solo raw",
        ),
    }
    cleaned = write_corpus(tmp_path / "cleaned", cleaned_rows)
    raw = write_corpus(tmp_path / "raw", raw_rows)
    config = config_for(tmp_path, raw_corpus=raw, cleaned_corpus=cleaned)
    evaluation = benchmark.build_evaluation_set(
        cleaned,
        "all",
        seed=42,
        per_language=100,
    )

    texts, labels, metadata = benchmark.prepare_training_data(
        config,
        "raw",
        "all",
        evaluation,
    )

    training_keys = {benchmark.normalize_text(text) for text in texts}
    assert training_keys.isdisjoint(evaluation.normalized_keys)
    assert training_keys == {
        "cross label text",
        "raw-only english keeper",
        "mensaje español solo raw",
    }
    assert Counter(labels) == {"en": 2, "es": 2}
    assert metadata == {
        "training_rows": 4,
        "training_english": 2,
        "training_spanish": 2,
        "excluded_evaluation_occurrences": 10,
        "training_min_chars": 0,
    }
    assert metadata["excluded_evaluation_occurrences"] > len(
        evaluation.normalized_keys
    )


def test_minimum_character_training_variants_use_inclusive_thresholds(
    tmp_path: Path,
):
    rows = {
        **EMPTY_CORPUS,
        "advanced.csv": (
            "123456789",
            "1234567890",
            "123456789012345",
            "1234567890123456",
        ),
    }
    cleaned = write_corpus(tmp_path / "cleaned", rows)
    raw = write_corpus(tmp_path / "raw", rows)
    config = config_for(tmp_path, raw_corpus=raw, cleaned_corpus=cleaned)

    expected = {
        "cleaned": (
            {"123456789", "1234567890", "123456789012345", "1234567890123456"},
            0,
        ),
        "cleaned_min10": (
            {"1234567890", "123456789012345", "1234567890123456"},
            10,
        ),
        "cleaned_min16": ({"1234567890123456"}, 16),
    }
    for variant, (expected_texts, minimum) in expected.items():
        texts, labels, metadata = benchmark.prepare_training_data(
            config,
            variant,
            "all",
            empty_evaluation(),
        )
        assert set(texts) == expected_texts
        assert labels == ["en"] * len(expected_texts)
        assert metadata["training_rows"] == len(expected_texts)
        assert metadata["training_min_chars"] == minimum
        assert metadata["excluded_evaluation_occurrences"] == 0


def test_metric_rows_report_coverage_and_length_buckets():
    records = [
        record("lol", "en", 1),
        record("0123456789", "es", 2),
        record("0123456789abcdef", "en", 3),
        record("0123456789abcdefghijklmnopqrstu", "es", 4),
    ]
    predictions = ["en", "other", "es", "es"]
    timing = {"messages_per_second": 123.0}

    class TimingDetector:
        @staticmethod
        def predict(texts):
            return ["en"] * len(texts)

    rows = benchmark.metric_rows(
        {"detector": "fake"},
        records,
        predictions,
        timing,
        detector=TimingDetector(),
        latency_sample_size=2,
    )
    by_bucket = {row["length_bucket"]: row for row in rows}

    assert set(by_bucket) == {"all", "<10", "10-15", "16-30", "31+", "16+"}
    assert by_bucket["all"]["examples"] == 4
    assert by_bucket["all"]["accuracy"] == pytest.approx(0.5)
    assert by_bucket["all"]["coverage"] == pytest.approx(0.75)
    assert by_bucket["all"]["covered_accuracy"] == pytest.approx(2 / 3)
    assert by_bucket["all"]["abstentions"] == 1
    assert by_bucket["all"]["messages_per_second"] == 123.0
    assert by_bucket["all"]["timing_scope"] == "all"

    assert by_bucket["<10"]["examples"] == 1
    assert by_bucket["<10"]["accuracy"] == 1.0
    assert by_bucket["<10"]["timing_scope"] == "not_timed"
    assert by_bucket["10-15"]["coverage"] == 0.0
    assert by_bucket["10-15"]["covered_accuracy"] is None
    assert by_bucket["16-30"]["accuracy"] == 0.0
    assert by_bucket["31+"]["accuracy"] == 1.0
    assert by_bucket["16+"]["examples"] == 2
    assert by_bucket["16+"]["accuracy"] == pytest.approx(0.5)
    assert by_bucket["16+"]["coverage"] == 1.0
    assert by_bucket["16+"]["timing_scope"] == "16+"
    assert by_bucket["16+"]["timing_examples"] == 2


def test_standard_plan_has_expected_matrix_and_specialized_runs(tmp_path: Path):
    config = benchmark.BenchmarkConfig(
        raw_corpus=tmp_path / "raw",
        cleaned_corpus=tmp_path / "cleaned",
        output_dir=tmp_path / "output",
        package_detectors=(),
    )

    plan = benchmark.standard_local_plan(config)

    assert len(plan) == 64
    assert Counter(spec.detector for spec in plan) == {
        "rai_current_nb": 40,
        "rai_legacy_nb": 24,
    }
    assert Counter(spec.training_corpus for spec in plan) == {
        "raw": 24,
        "cleaned": 32,
        "cleaned_min10": 4,
        "cleaned_min16": 4,
    }
    assert Counter(spec.scenario for spec in plan) == {
        "all": 24,
        "beginner": 16,
        "advanced": 16,
        "beginner_to_advanced": 4,
        "advanced_to_beginner": 4,
    }
    assert Counter(spec.ngram_range for spec in plan) == {
        ngram_range: 16
        for ngram_range in benchmark.DEFAULT_NGRAM_RANGES
    }
    assert {
        (spec.training_corpus, spec.training_min_chars)
        for spec in plan
        if spec.training_corpus.startswith("cleaned_min")
    } == {("cleaned_min10", 10), ("cleaned_min16", 16)}
    assert all(
        spec.detector == "rai_current_nb"
        for spec in plan
        if "_to_" in spec.scenario
        or spec.training_corpus.startswith("cleaned_min")
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("2:5", (2, 5)),
        ("3,3", (3, 3)),
        ("2-4", (2, 4)),
        ("7", (7, 7)),
    ),
)
def test_parse_ngram_range_accepts_documented_forms(value, expected):
    assert benchmark.parse_ngram_range(value) == expected


@pytest.mark.parametrize("value", ("0:2", "3:2", "1:0"))
def test_parse_ngram_range_rejects_invalid_bounds(value):
    with pytest.raises(argparse.ArgumentTypeError, match="Invalid n-gram range"):
        benchmark.parse_ngram_range(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    (("0.1", 0.1), ("1", 1.0), ("0.625", 0.625)),
)
def test_parse_learning_fraction_accepts_unit_interval(value, expected):
    assert benchmark.parse_learning_fraction(value) == expected


@pytest.mark.parametrize("value", ("0", "-0.1", "1.01", "nan", "not-a-number"))
def test_parse_learning_fraction_rejects_invalid_values(value):
    with pytest.raises(argparse.ArgumentTypeError, match="0 < FRACTION <= 1"):
        benchmark.parse_learning_fraction(value)


def test_learning_curve_cli_builds_config_and_delegates(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    from cogs.utils import language_learning_curve

    captured = {}

    def fake_run(config):
        captured["config"] = config
        return SimpleNamespace(results=[{}, {}], skipped=[])

    monkeypatch.setattr(language_learning_curve, "run_learning_curve", fake_run)
    output_dir = tmp_path / "curve"
    exit_code = benchmark.main(
        [
            "learning-curve",
            "--cleaned-corpus",
            str(tmp_path / "cleaned"),
            "--raw-corpus",
            str(tmp_path / "raw"),
            "--output-dir",
            str(output_dir),
            "--training-variant",
            "cleaned_min10",
            "--training-view",
            "beginner",
            "--evaluation-view",
            "advanced",
            "--fractions",
            "0.25",
            "1",
            "--repeats",
            "3",
            "--detectors",
            "rai_current_nb",
            "--ngrams",
            "2:5",
            "--seed",
            "17",
            "--evaluation-per-language",
            "200",
        ]
    )

    config = captured["config"]
    assert exit_code == 0
    assert config.output_dir == output_dir
    assert config.training_variant == "cleaned_min10"
    assert config.training_view == "beginner"
    assert config.evaluation_view == "advanced"
    assert config.fractions == (0.25, 1.0)
    assert config.repeats == 3
    assert config.detectors == ("rai_current_nb",)
    assert config.ngram_ranges == ((2, 5),)
    assert config.seed == 17
    assert config.evaluation_per_language == 200
    assert "2 learning-curve metric rows" in capsys.readouterr().out


def test_markdown_report_renders_ranked_results_metadata_and_skips():
    artifacts = benchmark.RunArtifacts(
        results=[
            {
                "length_bucket": "all",
                "detector": "rai_current_nb",
                "training_corpus": "cleaned",
                "scenario": "all",
                "evaluation_view": "all",
                "adapter_scope": "English and Spanish",
                "ngram_min": 2,
                "ngram_max": 5,
                "examples": 4,
                "accuracy": 0.75,
                "macro_f1": 0.74,
                "coverage": 0.80,
                "covered_accuracy": 0.9375,
                "messages_per_second": 125.25,
            },
            {
                "length_bucket": "16+",
                "detector": "rai_current_nb",
                "training_corpus": "cleaned",
                "scenario": "all",
                "evaluation_view": "all",
                "adapter_scope": "English and Spanish",
                "ngram_min": 2,
                "ngram_max": 5,
                "examples": 4,
                "accuracy": 0.75,
                "macro_f1": 0.74,
                "coverage": 0.80,
                "covered_accuracy": 0.9375,
                "messages_per_second": 125.25,
                "initialization_seconds": 0.125,
                "training_seconds": 1.5,
                "serialized_model_bytes": 2 * 1024 * 1024,
            },
        ],
        skipped=[
            {
                "detector": "missing_detector",
                "scenario": "package_all",
                "reason": "DetectorUnavailableError: not installed",
            }
        ],
        metadata={
            "generated_at": "2026-07-27T00:00:00+00:00",
            "raw_hashes": {"advanced.csv": "raw-hash"},
            "cleaned_hashes": {"advanced.csv": "clean-hash"},
            "evaluation_sets": {
                "all": {
                    "selected_by_label": {"en": 2, "es": 2},
                    "conflicting_group_count": 1,
                    "digest": "evaluation-digest",
                }
            },
            "python_version": "3.test",
            "python_executable": "/python",
            "platform": "test-platform",
        },
    )

    report = benchmark.render_markdown_report(artifacts)

    assert "All runs are local/offline. No API-backed or paid detector" in report
    assert (
        "| 1 | rai_current_nb | cleaned | (2,5) | 75.00% | 74.00% | "
        "80.00% | 93.75% | 125.2 | 0.125 | 1.500 | 2.00 |"
    ) in report
    assert (
        "- `all`: {'en': 2, 'es': 2} selected, "
        "1 conflicting normalized groups excluded"
    ) in report
    assert "`missing_detector` / `package_all`" in report
    assert (
        "Completed metric rows: 2 (1 overall rows, 1 production-length rows)."
        in report
    )
