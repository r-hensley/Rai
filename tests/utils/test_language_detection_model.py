import csv
import logging
from pathlib import Path

import pytest

from cogs.utils import helper_functions as hf
from tests.discord_fakes import make_bot


SPANISH_FILES = {"principiante.csv", "avanzado.csv"}


def write_corpus(
    directory: Path,
    *,
    marker: str,
    rows_per_file: int = 2,
    filenames: tuple[str, ...] = hf.LANGUAGE_CORPUS_FILENAMES,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for filename in filenames:
        language = "spanish" if filename in SPANISH_FILES else "english"
        with (directory / filename).open(
            "w",
            encoding="utf-8",
            newline="",
        ) as target:
            writer = csv.writer(
                target,
                delimiter=" ",
                quotechar="|",
                lineterminator="\n",
            )
            for index in range(rows_per_file):
                writer.writerow(
                    (
                        index + 1,
                        4,
                        f"{marker} {language} message number {index}",
                    )
                )
    return directory


def corpus_path(root: Path, relative_parts: tuple[str, ...]) -> Path:
    return root.joinpath(*relative_parts)


def test_language_corpus_directory_prefers_complete_cleaned_corpus(
    monkeypatch,
    tmp_path,
):
    legacy = write_corpus(
        corpus_path(tmp_path, hf.LANGUAGE_CORPUS_LEGACY_DIRECTORY),
        marker="legacy",
    )
    cleaned = write_corpus(
        corpus_path(tmp_path, hf.LANGUAGE_CORPUS_CLEANED_DIRECTORY),
        marker="cleaned",
    )
    monkeypatch.setattr(hf, "dir_path", str(tmp_path))

    selected = hf._language_corpus_directory()

    assert selected is not None
    assert Path(selected) == cleaned
    assert Path(selected) != legacy


@pytest.mark.parametrize(
    "cleaned_filenames",
    (
        (),
        ("principiante.csv",),
        ("principiante.csv", "avanzado.csv", "beginner.csv"),
    ),
)
def test_language_corpus_directory_falls_back_wholly_to_legacy(
    monkeypatch,
    tmp_path,
    cleaned_filenames,
):
    legacy = write_corpus(
        corpus_path(tmp_path, hf.LANGUAGE_CORPUS_LEGACY_DIRECTORY),
        marker="legacy",
    )
    if cleaned_filenames:
        write_corpus(
            corpus_path(tmp_path, hf.LANGUAGE_CORPUS_CLEANED_DIRECTORY),
            marker="partial-cleaned",
            filenames=cleaned_filenames,
        )
    monkeypatch.setattr(hf, "dir_path", str(tmp_path))

    selected = hf._language_corpus_directory()

    assert selected is not None
    assert Path(selected) == legacy


def test_language_model_loader_uses_all_cleaned_rows_in_one_25gram_fit(
    monkeypatch,
    tmp_path,
):
    write_corpus(
        corpus_path(tmp_path, hf.LANGUAGE_CORPUS_LEGACY_DIRECTORY),
        marker="legacy",
        rows_per_file=3,
    )
    cleaned = write_corpus(
        corpus_path(tmp_path, hf.LANGUAGE_CORPUS_CLEANED_DIRECTORY),
        marker="cleaned",
        rows_per_file=2,
    )
    bot = make_bot()
    monkeypatch.setattr(hf, "dir_path", str(tmp_path))
    monkeypatch.setattr(hf.here, "bot", bot)
    fit_calls = []
    original_fit = hf.Pipeline.fit

    def record_fit(pipeline, messages, labels, **kwargs):
        fit_calls.append((list(messages), list(labels)))
        return original_fit(pipeline, messages, labels, **kwargs)

    monkeypatch.setattr(hf.Pipeline, "fit", record_fit)

    hf._pre_load_language_detection_model()

    pipeline = bot.langdetect
    vectorizer = pipeline.named_steps["vectorizer"]
    model = pipeline.named_steps["model"]
    assert vectorizer.ngram_range == (2, 5)
    assert list(model.classes_) == ["en", "sp"]
    # Two English files and two Spanish files, with two rows in each.
    # Seeing all four rows per class proves there is no retained 5% split or
    # self-filtering pass, and distinguishes this from the larger fallback.
    assert list(model.class_count_) == [4.0, 4.0]
    assert len(fit_calls) == 1
    fitted_messages, fitted_labels = fit_calls[0]
    assert len(fitted_messages) == 8
    assert fitted_labels == ["en"] * 4 + ["sp"] * 4
    assert Path(hf._language_corpus_directory()) == cleaned


def test_language_model_loader_fits_only_legacy_rows_after_partial_upload(
    monkeypatch,
    tmp_path,
    caplog,
):
    legacy = write_corpus(
        corpus_path(tmp_path, hf.LANGUAGE_CORPUS_LEGACY_DIRECTORY),
        marker="legacy",
        rows_per_file=3,
    )
    write_corpus(
        corpus_path(tmp_path, hf.LANGUAGE_CORPUS_CLEANED_DIRECTORY),
        marker="partial-cleaned",
        rows_per_file=5,
        filenames=("principiante.csv",),
    )
    bot = make_bot()
    monkeypatch.setattr(hf, "dir_path", str(tmp_path))
    monkeypatch.setattr(hf.here, "bot", bot)

    with caplog.at_level(logging.WARNING):
        hf._pre_load_language_detection_model()

    vectorizer = bot.langdetect.named_steps["vectorizer"]
    model = bot.langdetect.named_steps["model"]
    features = set(vectorizer.get_feature_names_out())
    assert Path(hf._language_corpus_directory()) == legacy
    assert list(model.class_count_) == [6.0, 6.0]
    assert "legac" in features
    assert "parti" not in features
    assert "Cleaned language corpus is incomplete" in caplog.text


def test_language_model_loader_leaves_model_unset_when_no_corpus_is_complete(
    monkeypatch,
    tmp_path,
    caplog,
):
    write_corpus(
        corpus_path(tmp_path, hf.LANGUAGE_CORPUS_CLEANED_DIRECTORY),
        marker="partial-cleaned",
        filenames=("principiante.csv",),
    )
    bot = make_bot()
    monkeypatch.setattr(hf, "dir_path", str(tmp_path))
    monkeypatch.setattr(hf.here, "bot", bot)

    with caplog.at_level(logging.ERROR):
        hf._pre_load_language_detection_model()

    assert not hasattr(bot, "langdetect")
    assert "Language detection model not loaded, missing csv files" in caplog.text
