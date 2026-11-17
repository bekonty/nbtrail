"""Append-only, hash-chained event log (see SPEC.md §4–6)."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

FORMAT_VERSION = 1
GENESIS = "0" * 64
KINDS = {"session", "snapshot", "edit", "run", "paste"}
MAX_EVENT_BYTES = 1_000_000


class InvalidEvent(ValueError):
    """Raised when a client event does not match the spec."""


def canonical_json(obj: dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(event: dict[str, Any]) -> str:
    body = {k: v for k, v in event.items() if k != "hash"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def log_path_for(notebook: Path) -> Path:
    """``dir/hw.ipynb`` -> ``dir/.nbtrail/hw.ipynb.jsonl``"""
    return notebook.parent / ".nbtrail" / f"{notebook.name}.jsonl"


def validate(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise InvalidEvent("event must be an object")
    if event.get("kind") not in KINDS:
        raise InvalidEvent(f"unknown kind: {event.get('kind')!r}")
    if not isinstance(event.get("ts"), int):
        raise InvalidEvent("ts must be an integer (ms since epoch)")
    for reserved in ("v", "seq", "srv_ts", "prev", "hash"):
        if reserved in event:
            raise InvalidEvent(f"{reserved!r} is set by the server")
    if len(canonical_json(event).encode("utf-8")) > MAX_EVENT_BYTES:
        raise InvalidEvent("event too large")
    return event


class TrailLog:
    """One notebook's log file. Not safe for concurrent writers across processes."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._head: tuple[int, str] | None = None  # (next seq, last hash)
        self._size = -1  # file size when _head was computed

    def _disk_size(self) -> int:
        return self.path.stat().st_size if self.path.exists() else 0

    def _load_head(self) -> tuple[int, str]:
        # Re-read if the file changed under us (deleted, moved, edited elsewhere).
        if self._head is None or self._disk_size() != self._size:
            seq, last = 0, GENESIS
            if self.path.exists():
                for event in self.read():
                    seq, last = event["seq"] + 1, event["hash"]
            self._head = (seq, last)
            self._size = self._disk_size()
        return self._head

    def append(self, events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        """Validate, seal and append events. All-or-nothing per batch."""
        batch = [dict(validate(e)) for e in events]
        seq, prev = self._load_head()
        now = int(time.time() * 1000)
        sealed = []
        for event in batch:
            event.update(v=FORMAT_VERSION, seq=seq, srv_ts=now, prev=prev)
            event["hash"] = compute_hash(event)
            sealed.append(event)
            seq, prev = seq + 1, event["hash"]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.writelines(canonical_json(e) + "\n" for e in sealed)
        self._head = (seq, prev)
        self._size = self._disk_size()
        return sealed

    def read(self) -> Iterator[dict[str, Any]]:
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


@dataclass
class VerifyResult:
    ok: bool
    events: int
    bad_line: int | None = None  # 1-based, as shown in editors
    reason: str = ""


def verify(path: Path | str) -> VerifyResult:
    prev, count = GENESIS, 0
    with Path(path).open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                return VerifyResult(False, count, lineno, "not valid JSON")
            if event.get("seq") != count:
                return VerifyResult(False, count, lineno, f"expected seq {count}, found {event.get('seq')}")
            if event.get("prev") != prev:
                return VerifyResult(False, count, lineno, "chain broken: prev does not match previous hash")
            if compute_hash(event) != event.get("hash"):
                return VerifyResult(False, count, lineno, "content was modified: hash mismatch")
            prev, count = event["hash"], count + 1
    return VerifyResult(True, count)
