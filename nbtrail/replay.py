"""Rebuild notebook state from a log and summarise the process."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

IDLE_GAP_MS = 5 * 60 * 1000  # gaps longer than this don't count as active time


def apply_delta(text: str, delta: list[dict[str, Any]]) -> str:
    """Apply a Yjs text delta: [{retain:n} | {insert:s} | {delete:n}, ...]."""
    out, pos = [], 0
    for op in delta:
        if "retain" in op:
            out.append(text[pos : pos + op["retain"]])
            pos += op["retain"]
        elif "insert" in op:
            out.append(op["insert"])
        elif "delete" in op:
            pos += op["delete"]
    out.append(text[pos:])
    return "".join(out)


def state_at(events: Iterable[dict[str, Any]], upto: int | None = None) -> list[dict[str, Any]]:
    """Cells (id, type, source) after event ``upto`` (inclusive); default = end."""
    cells: list[dict[str, Any]] = []
    for e in events:
        if upto is not None and e["seq"] > upto:
            break
        if e["kind"] == "snapshot":
            cells = [dict(c) for c in e["cells"]]
        elif e["kind"] == "edit":
            for c in cells:
                if c["id"] == e["cell"]:
                    c["source"] = apply_delta(c["source"], e["delta"])
                    break
    return cells


@dataclass
class Summary:
    events: int = 0
    active_minutes: float = 0.0
    runs: int = 0
    failed_runs: int = 0
    error_types: dict[str, int] = field(default_factory=dict)
    error_fix_cycles: int = 0
    chars_typed: int = 0
    chars_pasted: int = 0
    pastes: int = 0
    largest_paste: int = 0

    @property
    def typed_share(self) -> float:
        total = self.chars_typed + self.chars_pasted
        return self.chars_typed / total if total else 1.0


def summarize(events: Iterable[dict[str, Any]]) -> Summary:
    s = Summary()
    last_ts: int | None = None
    failing: set[str] = set()
    pending_paste: dict[str, int] = {}  # cell -> chars about to arrive via edit
    for e in events:
        s.events += 1
        if last_ts is not None and 0 < e["ts"] - last_ts <= IDLE_GAP_MS:
            s.active_minutes += (e["ts"] - last_ts) / 60000
        last_ts = e["ts"]
        kind = e["kind"]
        if kind == "run":
            s.runs += 1
            if e.get("ok"):
                if e["cell"] in failing:
                    s.error_fix_cycles += 1
                    failing.discard(e["cell"])
            else:
                s.failed_runs += 1
                name = e.get("error") or "Error"
                s.error_types[name] = s.error_types.get(name, 0) + 1
                failing.add(e["cell"])
        elif kind == "paste":
            s.pastes += 1
            s.largest_paste = max(s.largest_paste, e["chars"])
            pending_paste[e["cell"]] = pending_paste.get(e["cell"], 0) + e["chars"]
        elif kind == "edit":
            inserted = sum(len(op["insert"]) for op in e["delta"] if "insert" in op)
            pasted = min(inserted, pending_paste.pop(e.get("cell"), 0))
            s.chars_pasted += pasted
            s.chars_typed += inserted - pasted
    s.active_minutes = round(s.active_minutes, 1)
    return s
