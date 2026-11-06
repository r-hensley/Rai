import asyncio
from contextlib import closing
import json
import sqlite3
import traceback

import pytest

from cogs.utils.traceback_store import TracebackStore


class ProviderError(Exception):
    def __init__(self, query, status, code):
        super().__init__(f"GET /translate?q={query}&lang=en failed")
        self.status = status
        self.code = code


def request(query, status, code):
    raise ProviderError(query, status, code)


def translate(*args):
    request(*args)


def menu(*args):
    translate(*args)


def other_operation(*args):
    raise ProviderError(*args)


def capture(caller, query, status=503, code=1):
    try:
        caller(query, status, code)
    except ProviderError as error:
        return error, "".join(traceback.format_exception(error))


@pytest.mark.asyncio
async def test_groups_paths_events_and_restart(tmp_path):
    filename = tmp_path / "tracebacks.db"
    store = TracebackStore(filename)
    store.initialize()

    async def record(args):
        error, sample = capture(*args)
        return await store.record_exception(error, "translation", sample)

    # All four of these are one failure. Two were reached through an extra caller.
    cases = [(translate, "猫"), (translate, "犬"), (menu, "雪"), (menu, "雪"),
             (translate, "猫", 403), (translate, "猫", 503, 2), (other_operation, "猫")]
    ids = await asyncio.gather(*(record(case) for case in cases))
    assert len(set(ids)) == 7
    reopened = TracebackStore(filename)
    reopened.initialize()
    group, _ = reopened.lookup_event(ids[0], 101)
    assert reopened.lookup_event(ids[1], 102) == (group, None)
    for i, event_id in enumerate(ids[2:4], start=103):
        assert reopened.lookup_event(event_id, i) == (group, None)
    reopened.mark_published(group, 987)
    assert reopened.lookup_event(ids[0], 101) == (group, 987)
    with closing(sqlite3.connect(filename)) as db:
        assert db.execute("SELECT occurrences, caller_paths FROM group_summary ORDER BY occurrences DESC").fetchall() == [
            (4, 2), (1, 1), (1, 1), (1, 1)]
        rows = db.execute("SELECT frames, sample_traceback FROM caller_paths WHERE group_id=?", (group,)).fetchall()
        assert sorted([frame[1] for frame in json.loads(frames)["frames"]] for frames, _ in rows) == [
            ["capture", "menu", "translate", "request"], ["capture", "translate", "request"]]
        assert all("Traceback (most recent call last)" in sample and "/translate?q=" in sample for _, sample in rows)
        key, = db.execute("SELECT signature FROM error_groups WHERE id=?", (group,)).fetchone()
        assert "q=<value>" in key and "503" in key
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.asyncio
async def test_cause_chain_and_exception_group_members_stay_distinguishable(tmp_path):
    store = TracebackStore(tmp_path / "tracebacks.db")
    store.initialize()

    def wrapped(exc):
        try:
            raise ExceptionGroup("multiple", [ValueError("empty response"), exc])
        except ExceptionGroup as cause:
            try:
                raise RuntimeError("translation failed") from cause
            except RuntimeError as error:
                return error

    for nested in [KeyError("language"), KeyError("language"), KeyError("auth")]:
        error = wrapped(nested)
        await store.record_exception(error, "translation", "".join(traceback.format_exception(error)))

    with closing(sqlite3.connect(store.filename)) as db:
        assert db.execute("SELECT occurrences FROM group_summary ORDER BY occurrences").fetchall() == [(1,), (2,)]
        frames, sample = db.execute("SELECT frames, sample_traceback FROM caller_paths LIMIT 1").fetchone()
        assert len(json.loads(frames)["cause"]["exceptions"]) == 2
        assert "ValueError: empty response" in sample and "direct cause" in sample


@pytest.mark.asyncio
async def test_provider_reason_preserved_with_same_code_and_varying_image_urls(tmp_path):
    store = TracebackStore(tmp_path / "archive.db")
    store.initialize()
    for reason, image in [("download failed", "1.png"), ("download failed", "2.png"), ("invalid format", "2.png")]:
        try:
            error = ValueError(f"{reason} for {image}")
            error.body = {"error": {"code": "invalid_image", "message": f"{reason} for https://example.org/{image}"}}
            raise error
        except ValueError as exc:
            await store.record_exception(exc, "inspect image", "".join(traceback.format_exception(exc)))
    with closing(sqlite3.connect(store.filename)) as db:
        assert db.execute("SELECT occurrences FROM group_summary ORDER BY occurrences").fetchall() == [(1,), (2,)]


@pytest.mark.asyncio
async def test_shared_rai_site_retains_different_library_and_feature_stacks(tmp_path, monkeypatch):
    from cogs.utils import traceback_store

    monkeypatch.setattr(traceback_store, "ROOT", tmp_path)
    source = tmp_path / "cogs" / "example.py"
    source.parent.mkdir()
    source.write_text(
        "def safe_send(operation):\n    operation()\n"
        "def welcome():\n    safe_send(send_message)\n"
        "def mute():\n    safe_send(create_dm)\n"
        "def edit():\n    send_message()\n"
    )

    def send_message():
        request("猫", 403, 50013)

    def create_dm():
        request("犬", 403, 50013)

    module = {"__name__": "cogs.example", "send_message": send_message, "create_dm": create_dm}
    exec(compile(source.read_text(), str(source), "exec"), module)
    store = TracebackStore(tmp_path / "archive.db")
    store.initialize()
    for caller in ("welcome", "mute", "edit"):
        try:
            module[caller]()
        except ProviderError as exc:
            await store.record_exception(exc, caller, "".join(traceback.format_exception(exc)))
    with closing(sqlite3.connect(store.filename)) as db:
        rows = db.execute("SELECT id, failure_site, occurrences, caller_paths FROM group_summary ORDER BY id").fetchall()
        assert [(site, events, paths) for _, site, events, paths in rows] == [
            ("cogs/example.py / safe_send / operation()", 2, 2),
            ("cogs/example.py / edit / send_message()", 1, 1),
        ]
        samples = db.execute("SELECT sample_traceback FROM caller_paths WHERE group_id=?", (rows[0][0],)).fetchall()
        assert any("in welcome" in sample and "in send_message" in sample for sample, in samples)
        assert any("in mute" in sample and "in create_dm" in sample for sample, in samples)
