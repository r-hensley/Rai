"""Local storage for Spanish-server hardcore decisions."""

import argparse
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import stat


WORKFLOW_VERSION = "v1.0.0"
TEXT_RETENTION = timedelta(days=90)
AUDIT_PATH = Path(__file__).resolve().parents[2] / "local/hardcore-audit/audit.sqlite"
DELETE_LOG_EXCLUDED_CHANNEL_IDS = frozenset({243858886266847233})


@dataclass(frozen=True)
class HardcoreEvaluation:
    mode: str
    original_text: str
    classifier_input: str
    corpus: str


class HardcoreAudit:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def _connect(self):
        directory = self.path.parent
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.is_symlink() or stat.S_IMODE(directory.stat().st_mode) & 0o077:
            raise PermissionError("Hardcore audit directory must be private")
        fd = os.open(self.path, os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
                raise PermissionError("Hardcore audit database must be a private regular file")
        finally:
            os.close(fd)
        with closing(sqlite3.connect(self.path, timeout=1)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA secure_delete = ON")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS outcome_counts (
                    day TEXT NOT NULL,
                    version TEXT NOT NULL,
                    target TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    corpus TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    count INTEGER NOT NULL,
                    PRIMARY KEY (day, version, target, mode, corpus, outcome)
                );
                CREATE TABLE IF NOT EXISTS deletions (
                    message_id INTEGER PRIMARY KEY,
                    recorded_at TEXT NOT NULL,
                    version TEXT NOT NULL,
                    target TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    corpus TEXT NOT NULL,
                    detected_language TEXT NOT NULL,
                    original_text TEXT NOT NULL,
                    classifier_input TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS deletions_recorded_at ON deletions(recorded_at);
            """)
            yield db

    def record(
        self, evaluation: HardcoreEvaluation, target: str, outcome: str, *,
        deletion: tuple[int, str] | None = None,
    ):
        now = datetime.now(timezone.utc)
        dimensions = (WORKFLOW_VERSION, target, evaluation.mode, evaluation.corpus)
        with self._connect() as db:
            if deletion is not None:
                message_id, detected_language = deletion
                inserted = db.execute("""
                    INSERT INTO deletions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(message_id) DO NOTHING
                """, (message_id, now.isoformat(), *dimensions, detected_language,
                      evaluation.original_text, evaluation.classifier_input))
                if not inserted.rowcount:
                    return
            db.execute("""
                INSERT INTO outcome_counts VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(day, version, target, mode, corpus, outcome)
                DO UPDATE SET count = count + 1
            """, (now.date().isoformat(), *dimensions, outcome))

    def expire(self, now: datetime | None = None):
        cutoff = (now or datetime.now(timezone.utc)) - TEXT_RETENTION
        with self._connect() as db:
            db.execute("DELETE FROM deletions WHERE recorded_at <= ?", (cutoff.isoformat(),))

    def read(self, section: str):
        if section == "deletions":
            self.expire()
            query = "SELECT * FROM deletions ORDER BY recorded_at, message_id"
        elif section == "summary":
            query = "SELECT * FROM outcome_counts ORDER BY day, version, target, mode, corpus, outcome"
        else:
            raise ValueError(f"Unknown audit section: {section}")
        with self._connect() as db:
            for row in db.execute(query):
                yield dict(row)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("section", choices=("summary", "deletions"))
    parser.add_argument("--database", type=Path, default=AUDIT_PATH)
    args = parser.parse_args()
    if not args.database.is_file():
        parser.exit(1, f"Audit database not found: {args.database}\n")
    for record in HardcoreAudit(args.database).read(args.section):
        print(json.dumps(record, ensure_ascii=False))
