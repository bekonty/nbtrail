"""Command line: ``nbtrail verify`` and ``nbtrail report``."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .log import TrailLog, log_path_for, verify
from .replay import summarize


def _resolve(target: str) -> Path:
    """Accept either a log file or the notebook it belongs to."""
    p = Path(target)
    if p.suffix == ".ipynb":
        p = log_path_for(p)
    if not p.exists():
        sys.exit(f"nbtrail: no log found at {p}")
    return p


def cmd_verify(args: argparse.Namespace) -> int:
    path = _resolve(args.target)
    result = verify(path)
    if result.ok:
        print(f"OK  {result.events} events, chain intact  ({path})")
        return 0
    print(f"FAIL  line {result.bad_line}: {result.reason}  ({path})")
    print(f"      the first {result.events} events are intact")
    return 1


def cmd_report(args: argparse.Namespace) -> int:
    path = _resolve(args.target)
    check = verify(path)
    s = summarize(TrailLog(path).read())
    if args.json:
        print(json.dumps({"verified": check.ok, **asdict(s), "typed_share": round(s.typed_share, 3)}, indent=2))
        return 0
    errors = ", ".join(f"{k}×{v}" for k, v in sorted(s.error_types.items(), key=lambda kv: -kv[1])) or "none"
    print(f"Process card — {path.name.removesuffix('.jsonl')}")
    print(f"  chain            {'intact' if check.ok else 'BROKEN at line ' + str(check.bad_line)}")
    print(f"  events           {s.events}")
    print(f"  active time      {s.active_minutes} min")
    print(f"  runs             {s.runs} ({s.failed_runs} failed)")
    print(f"  errors           {errors}")
    print(f"  error→fix cycles {s.error_fix_cycles}")
    print(f"  typed / pasted   {s.chars_typed} / {s.chars_pasted} chars  ({s.typed_share:.0%} typed)")
    print(f"  pastes           {s.pastes} (largest {s.largest_paste} chars)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nbtrail", description="Proof of process for Jupyter notebooks.")
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("verify", help="check that a log's hash chain is intact")
    v.add_argument("target", help="notebook (.ipynb) or log (.jsonl)")
    v.set_defaults(func=cmd_verify)
    r = sub.add_parser("report", help="summarise how a notebook was built")
    r.add_argument("target", help="notebook (.ipynb) or log (.jsonl)")
    r.add_argument("--json", action="store_true", help="machine-readable output")
    r.set_defaults(func=cmd_report)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
