"""Append-only audit trail (output/audit_trail.json).

One record per agent-loop step, plus a start and an end record for every
request, so an auditor can replay who did what, with which tool, and why the
team stopped. Records are only ever added; the file is never cleared.
"""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from safety import redact

ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = ROOT / "output" / "audit_trail.json"
SHORT_LIMIT = 300  # max characters kept for any args/result preview

_lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def short(value: Any, limit: int = SHORT_LIMIT) -> str:
    """Compact, redacted, length-capped text for the log."""
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    text = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    text = redact(" ".join(text.split()))
    return text if len(text) <= limit else text[: limit - 1] + "…"


def append_audit(record: dict) -> None:
    """Add one record to output/audit_trail.json without removing anything.

    Read the list, append, write to a temp file, then atomically replace. If the
    file is ever unreadable, it is kept as a backup instead of being overwritten.
    """
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {"time": now_iso(), **record}
    with _lock:
        entries: list = []
        if AUDIT_PATH.exists():
            try:
                entries = json.loads(AUDIT_PATH.read_text(encoding="utf-8") or "[]")
                if not isinstance(entries, list):
                    raise ValueError("audit trail is not a list")
            except ValueError:
                backup = AUDIT_PATH.with_name(f"audit_trail.corrupt-{datetime.now():%Y%m%d-%H%M%S}.json")
                AUDIT_PATH.rename(backup)
                entries = []
        entries.append(record)
        tmp = AUDIT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, AUDIT_PATH)
