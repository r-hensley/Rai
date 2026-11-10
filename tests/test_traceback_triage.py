"""Triage metadata preserves the archive and remains usable with older writers."""
from contextlib import closing
from datetime import datetime, timezone
import json
import sqlite3

import pytest

from cogs.utils.traceback_store import SCHEMA, TracebackStore


SAMPLE = "Traceback (most recent call last):\nValueError: test error\n"
FIX_COMMIT = "a" * 40


@pytest.fixture
def archive(tmp_path):
    store = TracebackStore(tmp_path / "tracebacks.db")
    store.initialize()
    first_event = store.record_text(SAMPLE, "2026-11-10T10:00:00+00:00", 100)
    group, _ = store.lookup_event(first_event, 100)
    return store, group, first_event


def summary(store, group):
    with closing(sqlite3.connect(store.filename)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM group_summary WHERE id=?", (group,)).fetchone()
        return dict(row)


def test_fresh_archive_has_untriaged_group(archive):
    store, group, _ = archive
    row = summary(store, group)
    assert row["status"] == "untriaged"
    assert row["triaged_at"] is None
    assert row["fix_confidence"] is None
    assert row["deployment_confirmed_at"] is None
    assert row["archived_at"] is None
    assert row["occurrences"] == 1


def test_migrate_v1_preserves_existing_records_and_view_columns(tmp_path):
    filename = tmp_path / "legacy.db"
    signature = json.dumps({"class": "builtins.ValueError", "diagnostic": {"message": "old"}})
    with closing(sqlite3.connect(filename)) as db, db:
        db.executescript(SCHEMA)
        db.execute("ALTER TABLE events ADD COLUMN rai_revision TEXT")
        db.execute("ALTER TABLE events ADD COLUMN botutils_revision TEXT")
        db.execute("ALTER TABLE events ADD COLUMN module_revisions TEXT")
        db.execute("CREATE VIEW group_summary AS SELECT * FROM error_groups")
        db.execute("PRAGMA user_version=1")
        db.execute("INSERT INTO error_groups VALUES (1, 'builtins.ValueError', 'old site', ?, 987)",
                   (signature,))
        db.execute("INSERT INTO caller_paths VALUES (1, 1, '{}', ?)", (SAMPLE,))
        db.execute("INSERT INTO events VALUES (1, 1, ?, 'old origin', 100, 'rai-rev', 'utils-rev', NULL)",
                   ("2026-11-10T10:00:00+00:00",))

    store = TracebackStore(filename)
    store.initialize()
    store.initialize()
    row = summary(store, 1)
    assert row["status"] == "untriaged"
    assert row["occurrences"] == 1
    assert row["forum_thread_id"] == 987
    assert row["exception_class"] == "ValueError"
    with closing(sqlite3.connect(filename)) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert db.execute("SELECT signature FROM error_groups").fetchone() == (signature,)
        assert db.execute("SELECT sample_traceback FROM caller_paths").fetchone() == (SAMPLE,)
        assert db.execute("SELECT id, origin, source_message_id, rai_revision, botutils_revision FROM events").fetchone() == (
            1, "old origin", 100, "rai-rev", "utils-rev")
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_triage_keeps_history_and_normalizes_deployment_time(archive):
    store, group, first_event = archive
    before = datetime.now(timezone.utc)
    first_review = store.triage_group(
        group, notes="Guard added, awaiting observation", status="monitoring",
        fix_commit=FIX_COMMIT, fix_confidence=4,
        deployment_confirmed_at="2026-11-10T05:00:00-08:00", reviewer="codex",
    )
    after = datetime.now(timezone.utc)
    row = summary(store, group)
    reviewed = datetime.fromisoformat(row["triaged_at"])
    assert reviewed.utcoffset().total_seconds() == 0
    assert before <= reviewed <= after
    assert row["deployment_confirmed_at"] == "2026-11-10T13:00:00+00:00"
    assert row["status"] == "monitoring"
    assert row["fix_confidence"] == 4
    assert row["fix_commit"] == FIX_COMMIT
    assert row["reviewer"] == "codex"
    assert row["reviewed_through_event_id"] == first_event
    assert row["events_since_triage"] == 0
    assert row["events_since_deployment"] == 0

    second_review = store.triage_group(group, notes="Reviewed the same issue again", fix_confidence=5,
                                     fix_commit=FIX_COMMIT)
    assert second_review > first_review
    assert summary(store, group)["notes"] == "Reviewed the same issue again"
    with closing(sqlite3.connect(store.filename)) as db:
        assert db.execute("SELECT notes, fix_confidence FROM group_triage WHERE group_id=? ORDER BY id",
                          (group,)).fetchall() == [
            ("Guard added, awaiting observation", 4), ("Reviewed the same issue again", 5)]
        assert db.execute("SELECT COUNT(*) FROM events").fetchone() == (1,)


@pytest.mark.parametrize("confidence", [0, 6, -1, True, False, 3.5, "4"])
def test_confidence_validation_does_not_append_invalid_review(archive, confidence):
    store, group, _ = archive
    with pytest.raises((TypeError, ValueError)):
        store.triage_group(group, notes="Invalid confidence", fix_confidence=confidence)
    assert summary(store, group)["status"] == "untriaged"


@pytest.mark.parametrize("stamp", ["2026-11-10T13:00:00", "2026-11-10", "not a date"])
def test_deployment_time_requires_valid_timezone(archive, stamp):
    store, group, _ = archive
    with pytest.raises((TypeError, ValueError)):
        store.triage_group(group, notes="Invalid deployment time", deployment_confirmed_at=stamp)
    assert summary(store, group)["triaged_at"] is None


def test_unknown_group_is_rejected(archive):
    store, _, _ = archive
    with pytest.raises((ValueError, KeyError)):
        store.triage_group(999999, notes="Unknown group")
    with closing(sqlite3.connect(store.filename)) as db:
        assert db.execute("SELECT COUNT(*) FROM group_triage").fetchone() == (0,)


def test_late_delivered_event_is_visible_after_archive_with_legacy_writer(archive):
    store, group, first_event = archive
    review = store.triage_group(group, notes="Archived after review", status="archived")
    row = summary(store, group)
    assert row["status"] == "archived"
    assert row["archived_at"] == row["triaged_at"]
    assert row["events_since_triage"] == 0

    # An older running recorder knows only these event columns. The timestamp
    # can predate triage when recording was delayed, so compare the event ID.
    with closing(sqlite3.connect(store.filename)) as db, db:
        path_id, = db.execute("SELECT caller_path_id FROM events WHERE id=?", (first_event,)).fetchone()
        db.execute("INSERT INTO events(caller_path_id, occurred_at, origin) VALUES (?, ?, ?)",
                   (path_id, "2026-11-09T00:00:00+00:00", "late report"))

    row = summary(store, group)
    assert row["status"] == "needs_review"
    assert row["events_since_triage"] == 1
    assert row["occurrences"] == 2
    assert row["reviewed_through_event_id"] == first_event
    with closing(sqlite3.connect(store.filename)) as db:
        assert db.execute("SELECT id, status FROM group_triage").fetchall() == [(review, "archived")]
        assert db.execute("SELECT sample_traceback FROM caller_paths").fetchone() == (SAMPLE,)

    store.triage_group(group, notes="Investigating recurrence", status="monitoring")
    row = summary(store, group)
    assert row["status"] == "monitoring"
    assert row["events_since_triage"] == 0
    assert row["occurrences"] == 2


def test_deployment_counter_uses_time_while_triage_counter_uses_review_watermark(archive):
    store, group, _ = archive
    store.record_text(SAMPLE, "2026-11-10T13:00:00+00:00", 101)
    store.triage_group(group, notes="Deployed earlier", status="monitoring", fix_commit=FIX_COMMIT,
                      fix_confidence=3, deployment_confirmed_at="2026-11-10T12:00:00+00:00")
    row = summary(store, group)
    assert row["events_since_triage"] == 0
    assert row["events_since_deployment"] == 1

    store.record_text(SAMPLE, "2026-11-10T14:00:00+00:00", 102)
    row = summary(store, group)
    assert row["events_since_triage"] == 1
    assert row["events_since_deployment"] == 2
    assert row["occurrences"] == 3
