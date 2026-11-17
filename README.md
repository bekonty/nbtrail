# nbtrail

**Proof of process for Jupyter.** nbtrail records *how* a notebook was built (edits, runs,
errors, fixes, pastes) into a tamper-evident, replayable log that the student owns and can
attach to a submission.

> When AI can write the final notebook in seconds, the final notebook proves nothing.
> The process does.

- **Sealed log.** Every event is SHA-256 chained to the one before it. Editing, deleting or
  reordering history breaks the chain, and `nbtrail verify` names the exact line.
- **Replayable.** The log rebuilds the notebook at any moment (snapshots + text deltas).
- **Process card.** Active time, runs, error→fix cycles, typed vs pasted code.
- **Visible and student-owned.** A `● nbtrail` badge sits in the toolbar. Click it to pause.
  Logs live next to the notebook and are never uploaded anywhere.

**It is not an AI detector.** It shows what happened. People decide what that means.

## Install

```bash
pip install nbtrail        # (once published)
```

Requires JupyterLab ≥ 4. Open any notebook and recording starts. The log is written to
`<notebook folder>/.nbtrail/<notebook>.jsonl`.

## Command line

```console
$ nbtrail verify hw/demo.ipynb
OK  21 events, chain intact  (hw/.nbtrail/demo.ipynb.jsonl)

$ nbtrail report hw/demo.ipynb
Process card — demo.ipynb
  chain            intact
  events           21
  active time      0.2 min
  runs             2 (1 failed)
  errors           NameError×1
  error→fix cycles 1
  typed / pasted   14 / 51 chars  (22% typed)
  pastes           1 (largest 51 chars)
```

(Real output from [`examples/demo.ipynb.jsonl`](examples/demo.ipynb.jsonl), recorded in a live
JupyterLab session.) Add `--json` for machine-readable output.

Edit one character in a log and `verify` catches it:

```console
$ nbtrail verify hw/demo.ipynb
FAIL  line 12: content was modified: hash mismatch
      the first 11 events are intact
```

## How it works

```
JupyterLab (TypeScript)            Jupyter server (Python)            Disk
┌────────────────────────┐  POST   ┌──────────────────────────┐       ┌───────────────────────────┐
│ Recorder               │ ──────▶ │ /nbtrail/events           │ ────▶ │ .nbtrail/<nb>.jsonl       │
│  · edit deltas (Yjs)   │ batches │  · validate               │append │  one sealed event / line  │
│  · runs + errors       │         │  · seq, server time       │       └───────────────────────────┘
│  · pastes (size)       │         │  · prev hash → hash       │
│  · snapshots           │         └──────────────────────────┘
└────────────────────────┘
```

The server seals events, so the browser never chooses hashes. Full format: [SPEC.md](SPEC.md).

**Limits (v0.1):** the log is tamper-*evident*, not tamper-*proof*. Someone with file access can
generate a brand-new chain or cut events off the end. Server-side anchoring (roadmap v0.3)
fixes that.

## Project layout

| Path | What |
|---|---|
| `src/recorder.ts` | Listens to one notebook: edits, runs, pastes, structure changes |
| `src/index.ts` | Plugin: one recorder per notebook, toolbar badge, pause command, settings |
| `nbtrail/log.py` | Hash-chained append-only log and `verify()` |
| `nbtrail/replay.py` | `apply_delta`, `state_at` (rebuild any moment), `summarize` |
| `nbtrail/routes.py` | `POST /nbtrail/events`, `GET /nbtrail/status` |
| `nbtrail/cli.py` | `nbtrail verify`, `nbtrail report` |
| `scripts/smoke_e2e.py` | Drives a real JupyterLab with Playwright and records a session |

## Development

```bash
pip install -e ".[test]"
jupyter labextension develop . --overwrite
jlpm build
jlpm watch          # terminal 1: rebuild on change
jupyter lab         # terminal 2
```

Tests:

```bash
pytest -q nbtrail   # 36 tests: hash chain, tampering, replay, API, CLI
jlpm test           # frontend (jest)
```

## Roadmap

- [x] v0.1: recorder, sealed log, `verify`, `report`, pause badge
- [ ] Merge consecutive keystrokes into one `edit` (smaller logs)
- [ ] Replay side panel: timeline slider, red error / purple paste markers
- [ ] HTML process card (`nbtrail report --html`)
- [ ] Anchoring: server signs the chain head so cut or rebuilt logs are detectable
- [ ] Instructor batch report over a folder of submissions

## License

BSD-3-Clause
