import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from cogs.utils import language_corpus
from cogs.utils.language_corpus import (
    CorpusBuildError,
    build_clean_corpus,
)


CORPUS_ROWS = {
    "advanced.csv": (
        "keep advanced",
        "hola mundo",
        "review foreign",
        "hello there",
    ),
    "beginner.csv": (
        "hola mundo",
        "keep beginner",
    ),
    "avanzado.csv": (
        "mensaje bueno",
        "hello there",
        "hola mundo",
    ),
    "principiante.csv": (
        "hello there",
        "mensaje español",
    ),
}


def encode_corpus_rows(messages: tuple[str, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(
        buffer,
        delimiter=" ",
        quotechar="|",
        lineterminator="\r\n",
    )
    for message in messages:
        writer.writerow((5, 3, message))
    return buffer.getvalue().encode("utf-8")


def write_audit(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=language_corpus.AUDIT_COLUMNS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def audit_row(
    filename: str,
    expected_language: str,
    original_line: int,
    text: str,
) -> dict[str, str]:
    return {
        "file": filename,
        "expected_language": expected_language,
        "original_line": str(original_line),
        "characters": str(len(text)),
        "text": text,
    }


@pytest.fixture
def corpus_world(tmp_path: Path) -> dict[str, object]:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    original_bytes = {}
    for filename, rows in CORPUS_ROWS.items():
        data = encode_corpus_rows(rows)
        (source_dir / filename).write_bytes(data)
        original_bytes[filename] = data

    explicit_audit = tmp_path / "explicit.tsv"
    review_audit = tmp_path / "review.tsv"
    write_audit(
        explicit_audit,
        [audit_row("advanced.csv", "English", 2, "hola mundo")],
    )
    write_audit(
        review_audit,
        [audit_row("avanzado.csv", "Spanish", 2, "hello there")],
    )
    return {
        "source_dir": source_dir,
        "explicit_audit": explicit_audit,
        "review_audit": review_audit,
        "original_bytes": original_bytes,
        "output_dir": tmp_path / "clean",
    }


def build(world: dict[str, object], **kwargs):
    return build_clean_corpus(
        source_dir=world["source_dir"],
        explicit_audit=world["explicit_audit"],
        review_audit=world["review_audit"],
        output_dir=world["output_dir"],
        **kwargs,
    )


def assert_sources_unchanged(world: dict[str, object]) -> None:
    source_dir = world["source_dir"]
    for filename, expected_bytes in world["original_bytes"].items():
        assert (source_dir / filename).read_bytes() == expected_bytes


def test_build_combines_audits_closes_same_language_duplicates_and_preserves_bytes(
    corpus_world,
):
    manifest = build(corpus_world)
    source_dir = corpus_world["source_dir"]
    output_dir = corpus_world["output_dir"]

    assert (output_dir / "advanced.csv").read_bytes() == b"".join(
        (source_dir / "advanced.csv").read_bytes().splitlines(keepends=True)[
            index
        ]
        for index in (0, 2, 3)
    )
    assert (output_dir / "beginner.csv").read_bytes() == b"".join(
        (source_dir / "beginner.csv").read_bytes().splitlines(keepends=True)[1:]
    )
    assert (output_dir / "avanzado.csv").read_bytes() == b"".join(
        (source_dir / "avanzado.csv").read_bytes().splitlines(keepends=True)[
            index
        ]
        for index in (0, 2)
    )
    assert (output_dir / "principiante.csv").read_bytes() == b"".join(
        (source_dir / "principiante.csv").read_bytes().splitlines(keepends=True)[
            1:
        ]
    )

    # Matching text on the other expected-language side is deliberately retained.
    assert b"hola mundo" in (output_dir / "avanzado.csv").read_bytes()
    assert b"hello there" in (output_dir / "advanced.csv").read_bytes()
    for filename in CORPUS_ROWS:
        output_data = (output_dir / filename).read_bytes()
        assert output_data.count(b"\n") == output_data.count(b"\r\n")

    assert manifest["totals"] == {
        "source_rows": 11,
        "output_rows": 7,
        "removed_rows": 4,
        "direct_audit_removals": 2,
        "exact_text_duplicate_closure_removals": 2,
    }
    assert {
        (removal["file"], removal["original_line"])
        for removal in manifest["removal_provenance"]
    } == {
        ("advanced.csv", 2),
        ("beginner.csv", 1),
        ("avanzado.csv", 2),
        ("principiante.csv", 1),
    }

    duplicate = next(
        removal
        for removal in manifest["removal_provenance"]
        if removal["file"] == "beginner.csv"
    )
    assert duplicate["reasons"] == [
        {
            "type": "same_expected_language_exact_text",
            "matched_audit_entries": [
                {
                    "file": "advanced.csv",
                    "original_line": 2,
                    "audit_lists": ["explicit_wrong"],
                }
            ],
        }
    ]

    disk_manifest = json.loads(
        (output_dir / language_corpus.MANIFEST_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    assert disk_manifest == manifest
    for filename, summary in manifest["files"].items():
        source = summary["source"]
        assert source["verified_unchanged"] is True
        assert (
            source["sha256_before_staging"]
            == source["sha256_after_staging"]
            == hashlib.sha256(corpus_world["original_bytes"][filename]).hexdigest()
        )
        assert summary["output"]["sha256"] == hashlib.sha256(
            (output_dir / filename).read_bytes()
        ).hexdigest()

    assert_sources_unchanged(corpus_world)


def test_exact_text_duplicate_closure_can_be_disabled(corpus_world):
    manifest = build(
        corpus_world,
        close_exact_text_duplicates=False,
    )
    output_dir = corpus_world["output_dir"]

    assert b"hola mundo" in (output_dir / "beginner.csv").read_bytes()
    assert b"hello there" in (output_dir / "principiante.csv").read_bytes()
    assert manifest["totals"]["removed_rows"] == 2
    assert manifest["totals"]["direct_audit_removals"] == 2
    assert manifest["totals"]["exact_text_duplicate_closure_removals"] == 0
    assert_sources_unchanged(corpus_world)


@pytest.mark.parametrize(
    ("changes", "error"),
    (
        ({"file": "../advanced.csv"}, "unknown corpus filename"),
        ({"expected_language": "Spanish"}, "requires 'English'"),
        ({"original_line": "0"}, "one-based positive integer"),
        ({"original_line": "999"}, "outside advanced.csv"),
        ({"characters": "999"}, "characters says 999"),
        (
            {"text": "adios mundo", "characters": str(len("adios mundo"))},
            "text does not exactly match",
        ),
    ),
)
def test_stale_or_invalid_audit_entries_fail_before_publishing(
    corpus_world,
    changes,
    error,
):
    bad_row = audit_row("advanced.csv", "English", 2, "hola mundo")
    bad_row.update(changes)
    write_audit(corpus_world["explicit_audit"], [bad_row])

    with pytest.raises(CorpusBuildError, match=error):
        build(corpus_world)

    assert not corpus_world["output_dir"].exists()
    assert_sources_unchanged(corpus_world)


def test_invalid_audit_header_fails_closed(corpus_world):
    corpus_world["explicit_audit"].write_text(
        "file\texpected_language\toriginal_line\ttext\n",
        encoding="utf-8",
    )

    with pytest.raises(CorpusBuildError, match="exactly these columns"):
        build(corpus_world)

    assert not corpus_world["output_dir"].exists()
    assert_sources_unchanged(corpus_world)


def test_existing_output_requires_explicit_overwrite(corpus_world):
    build(corpus_world)
    sentinel = corpus_world["output_dir"] / "do-not-lose.txt"
    sentinel.write_text("existing output", encoding="utf-8")

    with pytest.raises(CorpusBuildError, match="already exists"):
        build(corpus_world)
    assert sentinel.read_text(encoding="utf-8") == "existing output"

    manifest = build(corpus_world, overwrite=True)
    assert not sentinel.exists()
    assert (corpus_world["output_dir"] / "manifest.json").is_file()
    assert manifest["totals"]["removed_rows"] == 4
    assert_sources_unchanged(corpus_world)


def test_refuses_to_use_source_directory_as_output(corpus_world):
    corpus_world["output_dir"] = corpus_world["source_dir"]

    with pytest.raises(CorpusBuildError, match="replace or contain an input"):
        build(corpus_world, overwrite=True)

    assert_sources_unchanged(corpus_world)


def test_staging_failure_does_not_publish_partial_output(
    corpus_world,
    monkeypatch,
):
    real_write = language_corpus._write_and_sync
    calls = 0

    def fail_during_second_file(path, data):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated write failure")
        real_write(path, data)

    monkeypatch.setattr(
        language_corpus,
        "_write_and_sync",
        fail_during_second_file,
    )

    with pytest.raises(OSError, match="simulated write failure"):
        build(corpus_world)

    assert not corpus_world["output_dir"].exists()
    assert not list(
        corpus_world["output_dir"].parent.glob(
            f".{corpus_world['output_dir'].name}.staging-*"
        )
    )
    assert_sources_unchanged(corpus_world)


def test_cli_build_command(corpus_world, capsys):
    exit_code = language_corpus.main(
        [
            "build",
            "--source-dir",
            str(corpus_world["source_dir"]),
            "--explicit-audit",
            str(corpus_world["explicit_audit"]),
            "--review-audit",
            str(corpus_world["review_audit"]),
            "--output-dir",
            str(corpus_world["output_dir"]),
        ]
    )

    assert exit_code == 0
    assert "7 retained rows, 4 removed rows" in capsys.readouterr().out
    assert_sources_unchanged(corpus_world)
