"""Rai's local traceback archive. Only the shared error reporter writes new live events."""
import asyncio
from contextlib import closing
from datetime import datetime, timezone
import dis
from functools import lru_cache
import hashlib
import json
import linecache
import os
from pathlib import Path
import re
import sqlite3
import sys
import traceback


ROOT = Path(__file__).resolve().parents[2]

SCHEMA = """
CREATE TABLE IF NOT EXISTS error_groups (
    id INTEGER PRIMARY KEY,
    exception_class TEXT NOT NULL,
    failure_site TEXT NOT NULL,
    signature TEXT NOT NULL UNIQUE,
    forum_thread_id INTEGER
);
CREATE TABLE IF NOT EXISTS caller_paths (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES error_groups(id),
    frames TEXT NOT NULL,
    sample_traceback TEXT NOT NULL,
    UNIQUE(group_id, frames)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    caller_path_id INTEGER NOT NULL REFERENCES caller_paths(id),
    occurred_at TEXT NOT NULL,
    origin TEXT,
    source_message_id INTEGER UNIQUE
);
CREATE INDEX IF NOT EXISTS event_path ON events(caller_path_id);
CREATE VIEW IF NOT EXISTS group_summary AS
    SELECT g.id, g.exception_class, g.failure_site, COUNT(*) AS occurrences,
           COUNT(DISTINCT p.id) AS caller_paths, MIN(e.occurred_at) AS first_seen,
           MAX(e.occurred_at) AS last_seen, g.forum_thread_id
    FROM error_groups g JOIN caller_paths p ON p.group_id = g.id
    JOIN events e ON e.caller_path_id = p.id GROUP BY g.id;
"""


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _message_key(text):
    # Keep URL endpoints and parameter names. Query values include translated
    # text, credentials and request IDs. Preserve ordinary numbers such as errno.
    text = re.sub(r"([?&][\w.%~-]+=)[^&\s)'\"]*", r"\1<value>", text)
    text = re.sub(r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b", "<uuid>", text)
    text = re.sub(r"\b\d{17,20}\b", "<id>", text)
    return re.sub(r" at 0x[\da-fA-F]+>", " at <address>>", text)


def _diagnostic(error, previous):
    fields = {}
    for name in ("status", "status_code", "code", "errno", "type", "param", "name"):
        value = getattr(error, name, None)
        if isinstance(value, (int, str)) and value != "":
            fields[name] = value
    response_status = getattr(getattr(error, "response", None), "status_code", None)
    if isinstance(response_status, int):
        fields["status_code"] = response_status
    message = getattr(error, "text", None) or getattr(error, "strerror", None)
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        body = body.get("error", body)
        if isinstance(body, dict):
            for name in ("code", "type", "param"):
                if isinstance(body.get(name), (str, int)):
                    fields[name] = body[name]
            if isinstance(body.get("message"), str):
                message = body["message"]
                if body.get("code"):
                    # An API reason can quote the particular image or resource
                    # it rejected. Keep the reason as well as the provider code.
                    message = re.sub(r"""https?://[^\s)'"><]+""", "<url>", message)
    # E.g. keep Discord's field-specific validation reason as well as its code.
    message = str(message or error)
    # Command and network wrappers often repeat the entire inner diagnostic.
    # The nested exception already has its own structured identity.
    if previous is not None:
        inner = str(previous)
        if inner and message.endswith(inner):
            message = message[:-len(inner)] + "<chained exception>"
    fields["message"] = _message_key(message)
    return fields


@lru_cache(maxsize=4096)
def _statement_number(code, lineno, source):
    if not source:
        return lineno - code.co_firstlineno
    earlier_lines = {ln for _, ln in dis.findlinestarts(code) if ln and ln < lineno}
    return sum(linecache.getline(code.co_filename, ln).strip() == source for ln in earlier_lines)


def _stack(error):
    frames = []
    site = None
    tb = error.__traceback__
    summaries = traceback.extract_tb(tb, limit=sys.maxsize)
    for (frame, lineno), summary in zip(traceback.walk_tb(tb), summaries):
        code = frame.f_code
        filename = code.co_filename
        path = Path(filename)
        local = path.is_absolute() and path.is_relative_to(ROOT)
        relative = path.relative_to(ROOT) if local else None
        # Virtualenv libraries can live underneath the bot checkout.
        owned = local and (relative.parts[0] == "cogs" or relative.as_posix() == "Rai.py")
        module = frame.f_globals.get("__name__", "")
        file = relative.as_posix() if owned else module or filename
        source = linecache.getline(filename, lineno).strip()
        # Distinguish identical statements in one function without encoding the
        # absolute line number. Inserting unrelated lines preserves the key.
        occurrence = _statement_number(code, lineno, source)
        location = [file, code.co_qualname, source, occurrence, summary.colno]
        frames.append(location)
        if owned:
            site = location
    return frames, site or (frames[-1] if frames else None)


def _describe(error, ancestors=frozenset()):
    cls = f"{type(error).__module__}.{type(error).__qualname__}"
    if id(error) in ancestors:
        return {"class": cls, "cycle": True}, {}
    ancestors = ancestors | {id(error)}
    frames, site = _stack(error)
    previous = error.__cause__
    link = "cause"
    if previous is None and not error.__suppress_context__:
        previous = error.__context__
        link = "context"
    identity = {"class": cls, "site": site, "diagnostic": _diagnostic(error, previous)}
    path = {"frames": frames}
    if previous is not None:
        identity[link], path[link] = _describe(previous, ancestors)
    if isinstance(error, BaseExceptionGroup):
        members = [_describe(child, ancestors) for child in error.exceptions]
        identity["exceptions"] = [key for key, _ in members]
        path["exceptions"] = [calls for _, calls in members]
    return identity, path


class TracebackStore:
    def __init__(self, filename):
        self.filename = filename
        # Survive cog reloads while a forum post is in flight.
        self.forum_lock = asyncio.Lock()
        self.publishing: set[int] = set()

    def _connect(self):
        db = sqlite3.connect(self.filename, timeout=10)
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def initialize(self):
        # Full samples can contain the input or URL that triggered the error.
        os.close(os.open(self.filename, os.O_CREAT | os.O_RDWR, 0o600))
        with closing(self._connect()) as db:
            # A long investigation can read a snapshot while the bot keeps writing.
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript(SCHEMA)

    async def record_exception(self, error, origin, sample):
        occurred_at = datetime.now(timezone.utc).isoformat()
        return await asyncio.to_thread(self._record_exception, error, origin, sample, occurred_at)

    def _record_exception(self, error, origin, sample, occurred_at):
        signature, frames = _describe(error)
        if not signature["site"]:
            signature["origin"] = origin
        return self._insert(signature, frames, sample, occurred_at, origin)

    def record_text(self, text, occurred_at, message_id):
        # Older senders have no exception object. Keep an exact-text group in
        # its own namespace and make Discord redelivery idempotent.
        last_line = text.rstrip().splitlines()[-1] if text.strip() else ""
        name = last_line.partition(":")[0]
        signature = {"text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                     "class": name if re.fullmatch(r"[\w.]+", name) else "unclassified"}
        return self._insert(signature, {}, text, occurred_at, None, message_id)

    def _insert(self, signature, frames, sample, occurred_at, origin, message_id=None):
        key = _json(signature)
        stack = _json(frames)
        site = signature.get("site")
        label = f"{site[0]} / {site[1]} / {site[2]}" if site else "(no source site)"
        with closing(self._connect()) as db, db:
            if message_id is not None:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute("SELECT id FROM events WHERE source_message_id=?", (message_id,)).fetchone()
                if existing:
                    return existing[0]
            db.execute("INSERT INTO error_groups(exception_class, failure_site, signature) VALUES (?,?,?) "
                       "ON CONFLICT(signature) DO NOTHING", (signature["class"], label, key))
            group_id, = db.execute("SELECT id FROM error_groups WHERE signature=?", (key,)).fetchone()
            db.execute("INSERT INTO caller_paths(group_id, frames, sample_traceback) VALUES (?,?,?) "
                       "ON CONFLICT(group_id, frames) DO NOTHING", (group_id, stack, sample))
            path_id, = db.execute("SELECT id FROM caller_paths WHERE group_id=? AND frames=?",
                                  (group_id, stack)).fetchone()
            return db.execute("INSERT INTO events(caller_path_id, occurred_at, origin, source_message_id) "
                              "VALUES (?,?,?,?)", (path_id, occurred_at, origin, message_id)).lastrowid

    def lookup_event(self, event_id, message_id):
        """Attach a Discord message to the original event and find its forum group."""
        with closing(self._connect()) as db, db:
            db.execute("UPDATE events SET source_message_id=? WHERE id=? AND source_message_id IS NULL",
                       (message_id, event_id))
            return db.execute(
                "SELECT p.group_id, g.forum_thread_id FROM events e "
                "JOIN caller_paths p ON e.caller_path_id=p.id JOIN error_groups g ON g.id=p.group_id "
                "WHERE e.id=? AND e.source_message_id=?", (event_id, message_id)
            ).fetchone()

    def mark_published(self, group_id, thread_id):
        with closing(self._connect()) as db, db:
            db.execute("UPDATE error_groups SET forum_thread_id=? WHERE id=?", (thread_id, group_id))
