"""Startup-log attribution for a detector that was already loaded."""

import json
import os
from pathlib import Path


def process_identity(pid: int) -> str:
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return f"{boot_id}:{pid}:{fields[19]}"  # starttime is field 22 in /proc/PID/stat.


def session_corpus(path: Path) -> str | None:
    """Use the operator's attribution only for the identified Linux process."""
    try:
        attribution = json.loads(path.read_text())
        if attribution["process"] == process_identity(os.getpid()):
            corpus = attribution["corpus"]
            if isinstance(corpus, str) and corpus.strip():
                return corpus
    except (OSError, ValueError, IndexError, KeyError, TypeError):
        pass
    return None
