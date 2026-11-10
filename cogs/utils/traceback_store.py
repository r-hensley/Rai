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

from .loaded_revisions import LoadedRevisions, event_revisions, frame_revision


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
"""

TRIAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS group_triage (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES error_groups(id),
    triaged_at TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('triaged', 'monitoring', 'archived')),
    notes TEXT NOT NULL,
    fix_commit TEXT,
    fix_confidence INTEGER CHECK (fix_confidence BETWEEN 1 AND 5),
    deployment_confirmed_at TEXT,
    reviewed_through_event_id INTEGER NOT NULL
);
"""

GROUP_SUMMARY = """
CREATE VIEW group_summary AS
    WITH RECURSIVE chain(id, node, depth) AS (
        SELECT id, signature, 0 FROM error_groups
        UNION ALL
        SELECT id, coalesce(json_extract(node, '$.cause'), json_extract(node, '$.context')), depth + 1
        FROM chain WHERE json_type(node, '$.cause') = 'object' OR json_type(node, '$.context') = 'object'
    ), sites AS (
        SELECT id, depth, json_extract(node, '$.class') AS class,
               json_extract(node, '$.site[0]') AS file, json_extract(node, '$.site[1]') AS function,
               json_extract(node, '$.site[2]') AS statement
        FROM chain WHERE json_extract(node, '$.cycle') IS NULL
    ), ranked AS (
        SELECT *, first_value(class) OVER (PARTITION BY id ORDER BY depth DESC) AS cause_class,
               row_number() OVER (
            PARTITION BY id ORDER BY (file GLOB 'cogs/*' OR file = 'Rai.py') DESC,
                                     (file IS NOT NULL) DESC, depth DESC
        ) AS preference FROM sites
    )
    SELECT g.id, CASE WHEN r.cause_class LIKE 'builtins.%' THEN substr(r.cause_class, 10)
                      ELSE coalesce(r.cause_class, g.exception_class) END AS exception_class,
           coalesce(r.file || ' / ' || r.function || ' / ' || r.statement, g.failure_site) AS failure_site,
           COUNT(*) AS occurrences,
           COUNT(DISTINCT p.id) AS caller_paths, MIN(e.occurred_at) AS first_seen,
           MAX(e.occurred_at) AS last_seen, g.forum_thread_id,
           CASE WHEN t.status = 'archived' AND MAX(e.id) > t.reviewed_through_event_id
                THEN 'needs_review' ELSE coalesce(t.status, 'untriaged') END AS status,
           t.triaged_at, t.reviewer, t.notes, t.fix_commit, t.fix_confidence,
           t.deployment_confirmed_at, t.reviewed_through_event_id,
           CASE WHEN t.id IS NOT NULL THEN
               SUM(e.id > t.reviewed_through_event_id) END AS events_since_triage,
           CASE WHEN t.deployment_confirmed_at IS NOT NULL THEN
               SUM(julianday(e.occurred_at) >= julianday(t.deployment_confirmed_at))
               END AS events_since_deployment,
           CASE WHEN t.status = 'archived' THEN t.triaged_at END AS archived_at
    FROM error_groups g JOIN caller_paths p ON p.group_id = g.id
    JOIN events e ON e.caller_path_id = p.id
    LEFT JOIN ranked r ON r.id = g.id AND r.preference = 1
    LEFT JOIN group_triage t ON t.id = (
        SELECT MAX(latest.id) FROM group_triage latest WHERE latest.group_id = g.id
    ) GROUP BY g.id;
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


def _stack(error, revisions, versions):
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
        if owned or (local and relative.parts[0] == "web_admin"):
            name = relative.as_posix()
            versions.append((name, frame_revision(frame, name, revisions)))
        if owned:
            site = location
    return frames, site or (frames[-1] if frames else None)


def _describe(error, revisions, versions, ancestors=frozenset()):
    cls = f"{type(error).__module__}.{type(error).__qualname__}"
    if id(error) in ancestors:
        return {"class": cls, "cycle": True}, {}
    ancestors = ancestors | {id(error)}
    frames, site = _stack(error, revisions, versions)
    previous = error.__cause__
    link = "cause"
    if previous is None and not error.__suppress_context__:
        previous = error.__context__
        link = "context"
    identity = {"class": cls, "site": site, "diagnostic": _diagnostic(error, previous)}
    path = {"frames": frames}
    if previous is not None:
        identity[link], path[link] = _describe(previous, revisions, versions, ancestors)
    if isinstance(error, BaseExceptionGroup):
        members = [_describe(child, revisions, versions, ancestors) for child in error.exceptions]
        identity["exceptions"] = [key for key, _ in members]
        path["exceptions"] = [calls for _, calls in members]
    return identity, path


class TracebackStore:
    def __init__(self, filename):
        self.filename = filename
        self.revisions = None
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
        if self.revisions is None:
            self.revisions = LoadedRevisions(ROOT)
        with closing(self._connect()) as db, db:
            # A long investigation can read a snapshot while the bot keeps writing.
            db.execute("PRAGMA journal_mode = WAL")
            # Hold the write lock through the whole migration, including the view swap.
            db.executescript("BEGIN IMMEDIATE;\n" + SCHEMA)
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                db.execute("ALTER TABLE events ADD COLUMN rai_revision TEXT")
                db.execute("ALTER TABLE events ADD COLUMN botutils_revision TEXT")
                db.execute("ALTER TABLE events ADD COLUMN module_revisions TEXT")
            if version < 2:
                db.execute(TRIAGE_SCHEMA)
                db.execute("CREATE INDEX IF NOT EXISTS triage_group ON group_triage(group_id, id)")
                db.execute("DROP VIEW IF EXISTS group_summary")
                db.execute(GROUP_SUMMARY)
                db.execute("PRAGMA user_version=2")

    def triage_group(self, group_id, *, notes, status="triaged", fix_commit=None,
                     fix_confidence=None, deployment_confirmed_at=None, reviewer="codex"):
        """Append a complete review snapshot; retain all prior reviews and events.

        Confidence rates the proposed fix, not proof from quiet observation.
        Deployment confirmation marks when we know the fix was loaded, which
        can be later than the actual deployment. Archive state is reversible
        through another review; any later event makes it need review again.
        """
        if status not in ("triaged", "monitoring", "archived"):
            raise ValueError("Invalid triage status")
        if not isinstance(notes, str) or not notes.strip():
            raise ValueError("Triage notes are required")
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise ValueError("A reviewer is required")
        if fix_confidence is not None and (
            type(fix_confidence) is not int or not 1 <= fix_confidence <= 5
        ):
            raise ValueError("Fix confidence must be an integer from 1 to 5, or None")
        if deployment_confirmed_at is not None:
            confirmed = deployment_confirmed_at
            if isinstance(confirmed, str):
                confirmed = datetime.fromisoformat(confirmed)
            if not isinstance(confirmed, datetime) or confirmed.utcoffset() is None:
                raise ValueError("Deployment confirmation must include a timezone")
            deployment_confirmed_at = confirmed.astimezone(timezone.utc).isoformat()
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM error_groups WHERE id=?", (group_id,)).fetchone():
                raise ValueError(f"Unknown error group {group_id}")
            watermark, = db.execute(
                "SELECT coalesce(MAX(e.id), 0) FROM events e "
                "JOIN caller_paths p ON p.id=e.caller_path_id WHERE p.group_id=?",
                (group_id,),
            ).fetchone()
            return db.execute(
                "INSERT INTO group_triage(group_id, triaged_at, reviewer, status, notes, "
                "fix_commit, fix_confidence, deployment_confirmed_at, reviewed_through_event_id) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (group_id, datetime.now(timezone.utc).isoformat(), reviewer, status, notes,
                 fix_commit, fix_confidence, deployment_confirmed_at, watermark),
            ).lastrowid

    async def record_exception(self, error, origin, sample):
        occurred_at = datetime.now(timezone.utc).isoformat()
        revisions = self.revisions.snapshot()
        return await asyncio.to_thread(self._record_exception, error, origin, sample, occurred_at, revisions)

    def _record_exception(self, error, origin, sample, occurred_at, revisions):
        versions = []
        signature, frames = _describe(error, revisions, versions)
        if not signature["site"]:
            signature["origin"] = origin
        return self._insert(signature, frames, sample, occurred_at, origin,
                            revisions=event_revisions(versions, revisions))

    def record_text(self, text, occurred_at, message_id):
        # Older senders have no exception object. Keep an exact-text group in
        # its own namespace and make Discord redelivery idempotent.
        last_line = text.rstrip().splitlines()[-1] if text.strip() else ""
        name = last_line.partition(":")[0]
        signature = {"text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                     "class": name if re.fullmatch(r"[\w.]+", name) else "unclassified"}
        return self._insert(signature, {}, text, occurred_at, None, message_id)

    def _insert(self, signature, frames, sample, occurred_at, origin, message_id=None, revisions=None):
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
            rai, botutils, modules = revisions or (None, None, None)
            return db.execute(
                "INSERT INTO events(caller_path_id, occurred_at, origin, source_message_id, "
                "rai_revision, botutils_revision, module_revisions) VALUES (?,?,?,?,?,?,?)",
                (path_id, occurred_at, origin, message_id, rai, botutils, modules),
            ).lastrowid

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
