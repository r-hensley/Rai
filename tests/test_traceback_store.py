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


def test_upgrade_preserves_events_and_displays_underlying_rai_error(tmp_path):
    from cogs.utils.traceback_store import SCHEMA

    filename = tmp_path / "tracebacks.db"
    site = ["cogs/owner.py", "Owner.raise_error", "x = 1 / 0", 0, 12]
    error = {"class": "discord.CommandInvokeError", "site": ["discord.core", "wrapped", "raise outer", 0, 4],
             "cause": {"class": "builtins.ZeroDivisionError", "site": site}}
    with closing(sqlite3.connect(filename)) as db, db:
        # The original on-disk schema, including a view with the old labels.
        db.executescript(SCHEMA + "CREATE VIEW group_summary AS SELECT * FROM error_groups;")
        db.execute("INSERT INTO error_groups VALUES (1, 'discord.CommandInvokeError', 'outer site', ?, 123)",
                   (json.dumps(error),))
        db.execute("INSERT INTO caller_paths VALUES (1, 1, '{}', 'original sample')")
        db.executemany("INSERT INTO events VALUES (?, 1, '2026-11-06', 'raise_error', ?)", [(1, 11), (2, 12)])

    for _ in range(2):
        TracebackStore(filename).initialize()
    with closing(sqlite3.connect(filename)) as db:
        assert db.execute("SELECT exception_class, failure_site, occurrences, caller_paths, forum_thread_id "
                          "FROM group_summary").fetchone() == (
            "ZeroDivisionError", "cogs/owner.py / Owner.raise_error / x = 1 / 0", 2, 1, 123)
        assert db.execute("SELECT exception_class, signature FROM error_groups").fetchone() == (
            "discord.CommandInvokeError", json.dumps(error))
        assert db.execute("SELECT sample_traceback FROM caller_paths").fetchone() == ("original sample",)
        assert db.execute("SELECT id, source_message_id, rai_revision, botutils_revision, module_revisions "
                          "FROM events ORDER BY id").fetchall() == [(1, 11, None, None, None), (2, 12, None, None, None)]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.asyncio
async def test_loaded_revisions_follow_code_loads_instead_of_pulls(tmp_path, monkeypatch):
    import importlib
    import sys
    from types import ModuleType

    import cogs
    from cogs.utils import traceback_store
    from cogs.utils.loaded_revisions import LoadedRevisions

    monkeypatch.setattr(traceback_store, "ROOT", tmp_path)
    heads = ["rai-before", "utils-before"]
    monkeypatch.setattr(LoadedRevisions, "heads", lambda self: tuple(heads))
    store = TracebackStore(tmp_path / "archive.db")
    store.initialize()
    directory = tmp_path / "cogs"
    directory.mkdir()
    monkeypatch.setattr(cogs, "__path__", [str(directory), *cogs.__path__])
    failure_file = directory / "_traceback_test_failure.py"
    failure_file.write_text("def fail():\n    raise ValueError('failure')\n")
    (directory / "_traceback_test_caller.py").write_text("def call(func):\n    func()\n")
    name = "cogs._traceback_test_failure"
    caller_name = "cogs._traceback_test_caller"
    old_module = importlib.import_module(name)
    caller_module = importlib.import_module(caller_name)

    async def record(module):
        try:
            caller_module.call(module.fail)
        except ValueError as exc:
            return await store.record_exception(exc, "test", "".join(traceback.format_exception(exc)))

    try:
        await record(old_module)
        heads[:] = ["rai-after", "utils-after"]
        await record(old_module)  # pull alone
        async with store.revisions.loading():
            del sys.modules[name]  # discord.py replaces the module on cog reload
            new_module = importlib.import_module(name)
        await record(new_module)
        await record(old_module)  # a command still running with the old globals

        async with store.revisions.loading():
            reporter_name = "cogs.utils.BotUtils.bot_utils"
            reporter = ModuleType(reporter_name)
            reporter.__file__ = str(directory / "utils" / "BotUtils" / "bot_utils.py")
            monkeypatch.setitem(sys.modules, reporter_name, reporter)
        await record(new_module)

        with closing(sqlite3.connect(store.filename)) as db:
            rows = db.execute("SELECT rai_revision, botutils_revision, module_revisions FROM events ORDER BY id").fetchall()
            assert [row[:2] for row in rows] == [
                ("rai-before", "utils-before"), ("rai-before", "utils-before"), ("rai-after", "utils-before"),
                ("rai-before", "utils-before"), ("rai-after", "utils-after")]
            assert json.loads(rows[2][2]) == [["cogs/_traceback_test_caller.py", "rai-before"]]
            assert db.execute("SELECT occurrences, caller_paths FROM group_summary").fetchall() == [(5, 1)]

        old_function = new_module.fail
        failure_file.write_text("def fail():\n    raise ValueError('different failure')\n")
        async with store.revisions.loading():
            importlib.reload(new_module)  # support-module reload reuses globals
        try:
            old_function()
        except ValueError as exc:
            await store.record_exception(exc, "old callback", "".join(traceback.format_exception(exc)))
        await record(new_module)
        with closing(sqlite3.connect(store.filename)) as db:
            assert db.execute("SELECT rai_revision FROM events ORDER BY id DESC LIMIT 2").fetchall() == [
                ("rai-after",), (None,)]
    finally:
        sys.modules.pop(name, None)
        sys.modules.pop(caller_name, None)


def test_git_revision_requires_its_own_clean_python_checkout(tmp_path):
    import subprocess
    from cogs.utils.loaded_revisions import _revision

    def git(*args):
        return subprocess.check_output(["git", "-C", tmp_path, *args], text=True).strip()

    git("init", "--quiet")
    source = tmp_path / "bot.py"
    source.write_text("pass\n")
    git("add", "bot.py")
    git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "initial")
    assert _revision(tmp_path) == git("rev-parse", "HEAD")
    child = tmp_path / "missing-submodule"
    child.mkdir()
    assert _revision(child) is None
    (child / "untracked.py").write_text("pass\n")
    assert _revision(tmp_path) is None
    (child / "untracked.py").unlink()
    source.write_text("x = 1\n")
    assert _revision(tmp_path) is None


def test_summary_pairs_library_cause_with_rai_call_site_and_handles_text_only(tmp_path):
    store = TracebackStore(tmp_path / "archive.db")
    store.initialize()
    error = {"class": "RuntimeError", "site": ["cogs/example.py", "run", "request()", 0, 4],
             "context": {"class": "builtins.TimeoutError", "site": ["http", "read", "recv()", 0, 4]}}
    store._insert(error, {}, "saved", "2026-11-06", "command")
    store.record_text("ValueError: example", "2026-11-06", 123)
    with closing(sqlite3.connect(store.filename)) as db:
        assert db.execute("SELECT exception_class, failure_site FROM group_summary ORDER BY id").fetchall() == [
            ("TimeoutError", "cogs/example.py / run / request()"), ("ValueError", "(no source site)")]
        assert db.execute("SELECT rai_revision, botutils_revision FROM events WHERE source_message_id=123").fetchone() == (
            None, None)
