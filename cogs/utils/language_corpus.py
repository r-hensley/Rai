"""Build a cleaned, auditable copy of Rai's language corpora.

The source corpora are treated as immutable snapshots.  Audit entries are
validated against their exact source filename, one-based physical line,
character count, and message text before any output is written.  Retained
records are copied as bytes so their CSV representation and line endings are
not changed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


MANIFEST_FILENAME = "manifest.json"
MANIFEST_SCHEMA_VERSION = 1
AUDIT_COLUMNS = (
    "file",
    "expected_language",
    "original_line",
    "characters",
    "text",
)


class CorpusBuildError(RuntimeError):
    """Raised when a safe derived corpus cannot be built."""


@dataclass(frozen=True)
class CorpusSpec:
    filename: str
    expected_language: str


CORPUS_SPECS = (
    CorpusSpec("advanced.csv", "English"),
    CorpusSpec("beginner.csv", "English"),
    CorpusSpec("avanzado.csv", "Spanish"),
    CorpusSpec("principiante.csv", "Spanish"),
)
CORPUS_SPEC_BY_FILENAME = {spec.filename: spec for spec in CORPUS_SPECS}


@dataclass(frozen=True)
class SourceCorpus:
    spec: CorpusSpec
    path: Path
    data: bytes
    physical_rows: tuple[bytes, ...]
    messages: tuple[str, ...]
    sha256: str


@dataclass(frozen=True)
class AuditInput:
    category: str
    path: Path
    data: bytes
    sha256: str
    row_count: int


@dataclass(frozen=True, order=True)
class AuditTarget:
    filename: str
    original_line: int
    expected_language: str
    characters: int
    text: str


_POSITIVE_INTEGER = re.compile(r"[1-9][0-9]*\Z")
_NONNEGATIVE_INTEGER = re.compile(r"[0-9]+\Z")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise CorpusBuildError(f"Could not re-read input {path}: {exc}") from exc
    return digest.hexdigest()


def _physical_lines(data: bytes) -> tuple[bytes, ...]:
    """Split on LF while retaining every byte in each physical line."""

    lines = []
    start = 0
    while start < len(data):
        newline = data.find(b"\n", start)
        if newline == -1:
            lines.append(data[start:])
            break
        lines.append(data[start : newline + 1])
        start = newline + 1
    return tuple(lines)


def _parse_corpus_line(path: Path, line_number: int, raw_line: bytes) -> str:
    try:
        decoded = raw_line.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CorpusBuildError(
            f"{path} line {line_number} is not valid UTF-8: {exc}"
        ) from exc

    try:
        records = list(
            csv.reader(
                io.StringIO(decoded, newline=""),
                delimiter=" ",
                quotechar="|",
                strict=True,
            )
        )
    except csv.Error as exc:
        raise CorpusBuildError(
            f"{path} line {line_number} is not valid corpus CSV: {exc}"
        ) from exc

    if len(records) != 1 or len(records[0]) != 3:
        field_count = len(records[0]) if len(records) == 1 else "multiple records"
        raise CorpusBuildError(
            f"{path} line {line_number} must contain exactly three fields; "
            f"found {field_count}"
        )
    return records[0][2]


def _load_source_corpus(source_dir: Path, spec: CorpusSpec) -> SourceCorpus:
    path = source_dir / spec.filename
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CorpusBuildError(f"Could not read source corpus {path}: {exc}") from exc

    physical_rows = _physical_lines(data)
    messages = tuple(
        _parse_corpus_line(path, line_number, raw_line)
        for line_number, raw_line in enumerate(physical_rows, start=1)
    )
    return SourceCorpus(
        spec=spec,
        path=path,
        data=data,
        physical_rows=physical_rows,
        messages=messages,
        sha256=_sha256_bytes(data),
    )


def _parse_positive_integer(value: str, *, field: str, location: str) -> int:
    if not _POSITIVE_INTEGER.fullmatch(value):
        raise CorpusBuildError(
            f"{location}: {field} must be a one-based positive integer, got {value!r}"
        )
    return int(value)


def _parse_nonnegative_integer(value: str, *, field: str, location: str) -> int:
    if not _NONNEGATIVE_INTEGER.fullmatch(value):
        raise CorpusBuildError(
            f"{location}: {field} must be a nonnegative integer, got {value!r}"
        )
    return int(value)


def _read_audit(
    path: Path,
    category: str,
    sources: Mapping[str, SourceCorpus],
) -> tuple[AuditInput, tuple[AuditTarget, ...]]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CorpusBuildError(f"Could not read audit table {path}: {exc}") from exc

    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CorpusBuildError(f"Audit table {path} is not valid UTF-8: {exc}") from exc

    try:
        reader = csv.DictReader(
            io.StringIO(decoded, newline=""),
            delimiter="\t",
            strict=True,
        )
        if tuple(reader.fieldnames or ()) != AUDIT_COLUMNS:
            raise CorpusBuildError(
                f"Audit table {path} must have exactly these columns in order: "
                f"{', '.join(AUDIT_COLUMNS)}"
            )

        targets = []
        seen_in_table = set()
        for audit_line, row in enumerate(reader, start=2):
            location = f"{path} line {audit_line}"
            if None in row or any(row[column] is None for column in AUDIT_COLUMNS):
                raise CorpusBuildError(
                    f"{location}: row does not match the required TSV columns"
                )

            filename = row["file"]
            if filename not in CORPUS_SPEC_BY_FILENAME:
                allowed = ", ".join(spec.filename for spec in CORPUS_SPECS)
                raise CorpusBuildError(
                    f"{location}: unknown corpus filename {filename!r}; "
                    f"expected one of {allowed}"
                )

            source = sources[filename]
            expected_language = row["expected_language"]
            if expected_language != source.spec.expected_language:
                raise CorpusBuildError(
                    f"{location}: expected_language is {expected_language!r}, "
                    f"but {filename} requires {source.spec.expected_language!r}"
                )

            original_line = _parse_positive_integer(
                row["original_line"],
                field="original_line",
                location=location,
            )
            if original_line > len(source.messages):
                raise CorpusBuildError(
                    f"{location}: original_line {original_line} is outside "
                    f"{filename}'s {len(source.messages)} physical lines"
                )

            characters = _parse_nonnegative_integer(
                row["characters"],
                field="characters",
                location=location,
            )
            text = row["text"]
            if characters != len(text):
                raise CorpusBuildError(
                    f"{location}: characters says {characters}, but the audit text "
                    f"contains {len(text)} characters"
                )

            source_text = source.messages[original_line - 1]
            if text != source_text:
                raise CorpusBuildError(
                    f"{location}: text does not exactly match "
                    f"{filename} line {original_line}"
                )

            key = (filename, original_line)
            if key in seen_in_table:
                raise CorpusBuildError(
                    f"{location}: duplicate audit target {filename} line "
                    f"{original_line} in the same table"
                )
            seen_in_table.add(key)
            targets.append(
                AuditTarget(
                    filename=filename,
                    original_line=original_line,
                    expected_language=expected_language,
                    characters=characters,
                    text=text,
                )
            )
    except csv.Error as exc:
        raise CorpusBuildError(f"Audit table {path} is not valid TSV: {exc}") from exc

    return (
        AuditInput(
            category=category,
            path=path,
            data=data,
            sha256=_sha256_bytes(data),
            row_count=len(targets),
        ),
        tuple(targets),
    )


def _validate_output_location(
    output_dir: Path,
    source_dir: Path,
    audit_paths: Iterable[Path],
) -> None:
    if output_dir.is_symlink():
        raise CorpusBuildError(f"Output directory may not be a symlink: {output_dir}")

    output_resolved = output_dir.resolve()
    protected_inputs = [source_dir.resolve()]
    protected_inputs.extend(path.resolve() for path in audit_paths)

    for protected in protected_inputs:
        if protected == output_resolved or protected.is_relative_to(output_resolved):
            raise CorpusBuildError(
                f"Output directory {output_dir} would replace or contain an input "
                f"path ({protected})"
            )


def _write_and_sync(path: Path, data: bytes) -> None:
    with path.open("xb") as file:
        file.write(data)
        file.flush()
        os.fsync(file.fileno())


def _publish_staging_directory(
    staging_dir: Path,
    output_dir: Path,
    *,
    overwrite: bool,
) -> None:
    output_exists = output_dir.exists() or output_dir.is_symlink()
    if output_exists and not overwrite:
        raise CorpusBuildError(
            f"Output directory already exists: {output_dir}. "
            "Pass overwrite=True (or --overwrite) to replace it."
        )
    if output_exists and (output_dir.is_symlink() or not output_dir.is_dir()):
        raise CorpusBuildError(
            f"Refusing to replace a non-directory or symlink output: {output_dir}"
        )

    if not output_exists:
        try:
            os.replace(staging_dir, output_dir)
        except OSError as exc:
            raise CorpusBuildError(
                f"Could not publish staged corpus to {output_dir}: {exc}"
            ) from exc
        return

    backup_dir = output_dir.parent / (
        f".{output_dir.name}.backup-{uuid.uuid4().hex}"
    )
    try:
        os.replace(output_dir, backup_dir)
        try:
            os.replace(staging_dir, output_dir)
        except BaseException:
            os.replace(backup_dir, output_dir)
            raise
    except OSError as exc:
        raise CorpusBuildError(
            f"Could not atomically replace output directory {output_dir}: {exc}"
        ) from exc

    shutil.rmtree(backup_dir)


def _build_removal_provenance(
    sources: Mapping[str, SourceCorpus],
    target_categories: Mapping[tuple[str, int], set[str]],
    targets_by_key: Mapping[tuple[str, int], AuditTarget],
    *,
    close_exact_text_duplicates: bool,
) -> dict[tuple[str, int], dict[str, Any]]:
    removals: dict[tuple[str, int], dict[str, Any]] = {}
    audited_texts: dict[str, dict[str, list[AuditTarget]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for key, target in targets_by_key.items():
        categories = sorted(target_categories[key])
        removals[key] = {
            "file": target.filename,
            "expected_language": target.expected_language,
            "original_line": target.original_line,
            "characters": target.characters,
            "text": target.text,
            "reasons": [
                {
                    "type": "audit_entry",
                    "audit_lists": categories,
                }
            ],
        }
        audited_texts[target.expected_language][target.text].append(target)

    if not close_exact_text_duplicates:
        return removals

    for spec in CORPUS_SPECS:
        source = sources[spec.filename]
        language_texts = audited_texts[spec.expected_language]
        for original_line, text in enumerate(source.messages, start=1):
            key = (spec.filename, original_line)
            if key in removals or text not in language_texts:
                continue

            matched_entries = []
            for target in sorted(language_texts[text]):
                target_key = (target.filename, target.original_line)
                matched_entries.append(
                    {
                        "file": target.filename,
                        "original_line": target.original_line,
                        "audit_lists": sorted(target_categories[target_key]),
                    }
                )

            removals[key] = {
                "file": spec.filename,
                "expected_language": spec.expected_language,
                "original_line": original_line,
                "characters": len(text),
                "text": text,
                "reasons": [
                    {
                        "type": "same_expected_language_exact_text",
                        "matched_audit_entries": matched_entries,
                    }
                ],
            }

    return removals


def _verify_inputs_unchanged(
    sources: Mapping[str, SourceCorpus],
    audits: Sequence[AuditInput],
) -> tuple[dict[str, str], dict[str, str]]:
    source_hashes_after = {
        filename: _sha256_path(source.path)
        for filename, source in sources.items()
    }
    audit_hashes_after = {
        audit.category: _sha256_path(audit.path) for audit in audits
    }

    changed_sources = [
        filename
        for filename, source in sources.items()
        if source_hashes_after[filename] != source.sha256
    ]
    changed_audits = [
        audit.category
        for audit in audits
        if audit_hashes_after[audit.category] != audit.sha256
    ]
    if changed_sources or changed_audits:
        details = []
        if changed_sources:
            details.append(f"source corpora: {', '.join(changed_sources)}")
        if changed_audits:
            details.append(f"audit tables: {', '.join(changed_audits)}")
        raise CorpusBuildError(
            "Inputs changed while the derived corpus was being staged ("
            + "; ".join(details)
            + "); no output was published"
        )

    return source_hashes_after, audit_hashes_after


def build_clean_corpus(
    *,
    source_dir: Path,
    explicit_audit: Path,
    review_audit: Path,
    output_dir: Path,
    close_exact_text_duplicates: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Build and atomically publish a cleaned copy of all four corpora.

    ``explicit_audit`` and ``review_audit`` are combined.  By default, any
    additional row with exactly the same message text as an audited row is
    removed when it is on the same expected-language side (English or Spanish).
    The original corpus and audit files are never opened for writing.
    """

    source_dir = Path(source_dir)
    explicit_audit = Path(explicit_audit)
    review_audit = Path(review_audit)
    output_dir = Path(output_dir)

    _validate_output_location(
        output_dir,
        source_dir,
        (explicit_audit, review_audit),
    )
    if output_dir.exists() and not overwrite:
        raise CorpusBuildError(
            f"Output directory already exists: {output_dir}. "
            "Pass overwrite=True (or --overwrite) to replace it."
        )

    sources = {
        spec.filename: _load_source_corpus(source_dir, spec)
        for spec in CORPUS_SPECS
    }
    explicit_input, explicit_targets = _read_audit(
        explicit_audit,
        "explicit_wrong",
        sources,
    )
    review_input, review_targets = _read_audit(
        review_audit,
        "review_only",
        sources,
    )
    audit_inputs = (explicit_input, review_input)

    targets_by_key: dict[tuple[str, int], AuditTarget] = {}
    target_categories: dict[tuple[str, int], set[str]] = defaultdict(set)
    for category, targets in (
        ("explicit_wrong", explicit_targets),
        ("review_only", review_targets),
    ):
        for target in targets:
            key = (target.filename, target.original_line)
            previous = targets_by_key.get(key)
            if previous is not None and previous != target:
                raise CorpusBuildError(
                    f"Conflicting audit entries for {target.filename} line "
                    f"{target.original_line}"
                )
            targets_by_key[key] = target
            target_categories[key].add(category)

    removals = _build_removal_provenance(
        sources,
        target_categories,
        targets_by_key,
        close_exact_text_duplicates=close_exact_text_duplicates,
    )

    retained_data: dict[str, bytes] = {}
    file_summaries: dict[str, dict[str, Any]] = {}
    for spec in CORPUS_SPECS:
        source = sources[spec.filename]
        removed_lines = {
            line
            for filename, line in removals
            if filename == spec.filename
        }
        output_data = b"".join(
            raw_line
            for line_number, raw_line in enumerate(source.physical_rows, start=1)
            if line_number not in removed_lines
        )
        retained_data[spec.filename] = output_data

        direct_count = sum(
            (spec.filename, line) in targets_by_key for line in removed_lines
        )
        duplicate_count = len(removed_lines) - direct_count
        file_summaries[spec.filename] = {
            "expected_language": spec.expected_language,
            "source": {
                "path": str(source.path.resolve()),
                "sha256_before_staging": source.sha256,
                "bytes": len(source.data),
                "rows": len(source.physical_rows),
            },
            "output": {
                "path": spec.filename,
                "sha256": _sha256_bytes(output_data),
                "bytes": len(output_data),
                "rows": len(source.physical_rows) - len(removed_lines),
            },
            "removed": {
                "total": len(removed_lines),
                "direct_audit": direct_count,
                "exact_text_duplicate_closure": duplicate_count,
            },
        }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.staging-",
            dir=output_dir.parent,
        )
    )
    published = False
    try:
        for spec in CORPUS_SPECS:
            _write_and_sync(
                staging_dir / spec.filename,
                retained_data[spec.filename],
            )

        source_hashes_after, audit_hashes_after = _verify_inputs_unchanged(
            sources,
            audit_inputs,
        )
        for filename, digest in source_hashes_after.items():
            file_summaries[filename]["source"][
                "sha256_after_staging"
            ] = digest
            file_summaries[filename]["source"]["verified_unchanged"] = True

        direct_removals = len(targets_by_key)
        duplicate_removals = len(removals) - direct_removals
        ordered_removals = [
            removals[(spec.filename, line)]
            for spec in CORPUS_SPECS
            for line in range(1, len(sources[spec.filename].physical_rows) + 1)
            if (spec.filename, line) in removals
        ]
        manifest: dict[str, Any] = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "created_at_utc": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "settings": {
                "close_exact_text_duplicates_within_expected_language": (
                    close_exact_text_duplicates
                ),
            },
            "input_integrity": {
                "verified_unchanged_after_staging": True,
            },
            "audits": {
                audit.category: {
                    "path": str(audit.path.resolve()),
                    "sha256_before_staging": audit.sha256,
                    "sha256_after_staging": audit_hashes_after[audit.category],
                    "verified_unchanged": True,
                    "rows": audit.row_count,
                }
                for audit in audit_inputs
            },
            "files": file_summaries,
            "totals": {
                "source_rows": sum(
                    len(source.physical_rows) for source in sources.values()
                ),
                "output_rows": sum(
                    summary["output"]["rows"]
                    for summary in file_summaries.values()
                ),
                "removed_rows": len(removals),
                "direct_audit_removals": direct_removals,
                "exact_text_duplicate_closure_removals": duplicate_removals,
            },
            "removal_provenance": ordered_removals,
        }
        manifest_data = (
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        _write_and_sync(staging_dir / MANIFEST_FILENAME, manifest_data)

        _publish_staging_directory(
            staging_dir,
            output_dir,
            overwrite=overwrite,
        )
        published = True
    finally:
        if not published and staging_dir.exists():
            shutil.rmtree(staging_dir)

    return manifest


def _build_parser() -> argparse.ArgumentParser:
    repository_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Build a validated, byte-preserving cleaned language corpus.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser(
        "build",
        help="validate both audit tables and build a derived corpus directory",
    )
    build_parser.add_argument(
        "--source-dir",
        type=Path,
        default=repository_root / "cogs" / "utils",
        help="directory containing the four source CSV files",
    )
    build_parser.add_argument(
        "--explicit-audit",
        type=Path,
        default=repository_root
        / ".codex"
        / "language-corpus-explicit-wrong.tsv",
    )
    build_parser.add_argument(
        "--review-audit",
        type=Path,
        default=repository_root / ".codex" / "language-corpus-review-only.tsv",
    )
    build_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="new directory to publish; existing directories require --overwrite",
    )
    build_parser.add_argument(
        "--no-close-exact-text-duplicates",
        dest="close_exact_text_duplicates",
        action="store_false",
        help="remove only directly audited rows, retaining unaudited exact duplicates",
    )
    build_parser.set_defaults(close_exact_text_duplicates=True)
    build_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="explicitly replace an existing output directory",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "build":
        try:
            manifest = build_clean_corpus(
                source_dir=args.source_dir,
                explicit_audit=args.explicit_audit,
                review_audit=args.review_audit,
                output_dir=args.output_dir,
                close_exact_text_duplicates=args.close_exact_text_duplicates,
                overwrite=args.overwrite,
            )
        except CorpusBuildError as exc:
            parser.error(str(exc))

        totals = manifest["totals"]
        print(
            f"Built {args.output_dir}: {totals['output_rows']} retained rows, "
            f"{totals['removed_rows']} removed rows."
        )
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
