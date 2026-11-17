# nbtrail — Specification (v0.1)

> Proof of process for Jupyter: a tamper-evident, replayable record of how a
> notebook was built, owned by the student who built it.

## 1. Problem

When AI can produce a finished notebook in seconds, the final `.ipynb` says
nothing about who did the thinking. Graders see only the end state; students
have no way to show their work. nbtrail records the *process* — edits, runs,
errors, fixes, pastes — so a student can attach evidence of it to a submission.

## 2. Non-goals

- **Not an AI detector.** nbtrail never claims "this was / wasn't written by
  AI". It shows what happened; humans interpret it.
- **Not surveillance.** Logs live next to the student's notebook, recording is
  visible and pausable, and the student decides what to share.
- **Not tamper-proof (v0.1).** It is tamper-*evident*: editing or reordering
  history breaks the hash chain. Someone with file access can still rebuild a
  whole new chain or cut events off the end. Server-side anchoring (§7) closes
  that gap in v0.2.

## 3. Architecture

```
JupyterLab (TypeScript)            Jupyter server (Python)            Disk
┌────────────────────────┐  POST   ┌──────────────────────────┐       ┌───────────────────────────┐
│ Recorder               │ ──────▶ │ /nbtrail/events           │ ────▶ │ <dir>/.nbtrail/<nb>.jsonl │
│  · edit deltas (Yjs)   │ batches │  · validates events       │append │  one sealed event / line  │
│  · runs + errors       │         │  · assigns seq + srv_ts   │       └───────────────────────────┘
│  · pastes (size only)  │         │  · hash-chains + appends  │                   │
│  · snapshots           │         └──────────────────────────┘                   ▼
└────────────────────────┘                                          CLI: nbtrail verify / report
```

The **server** seals events, not the browser, so the chain is built in one
place and the client cannot choose hashes.

## 4. Event format

One JSON object per line (JSONL). Fields set by the client:

| field  | type   | meaning |
|--------|--------|---------|
| `kind` | string | `session`, `snapshot`, `edit`, `run`, `paste` |
| `ts`   | int    | client time, ms since epoch |
| `cell` | string | cell id (absent for `session`, `snapshot`) |

Kind-specific fields:

| kind       | extra fields |
|------------|--------------|
| `session`  | `action`: `start` \| `pause` \| `resume` \| `stop` |
| `snapshot` | `cells`: `[{id, type, source}]` — full notebook state (keyframe) |
| `edit`     | `delta`: Yjs text delta, list of `{retain:n}` / `{insert:s}` / `{delete:n}` |
| `run`      | `ok`: bool, `error`: exception name or `null` |
| `paste`    | `chars`: int — size only, the text arrives through the `edit` delta |

Fields added by the server when sealing:

| field    | meaning |
|----------|---------|
| `v`      | format version (`1`) |
| `seq`    | 0-based position in the log |
| `srv_ts` | server receive time, ms since epoch |
| `prev`   | `hash` of the previous event; `"0"*64` for the first |
| `hash`   | `sha256(canonical_json(event without "hash"))` |

`canonical_json` = `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.

## 5. Rules

1. A `snapshot` is written when recording starts and whenever cells are added,
   removed or moved. Replay always starts from the latest snapshot at or before
   the target point (keyframes, like video).
2. Events are queued client-side and sent in batches (default every 2 s);
   a batch is sealed in order, all-or-nothing. v0.1 sends one `edit` per
   keystroke; merging consecutive edits to the same cell is on the roadmap.
3. Events larger than 1 MB, unknown kinds, or paths outside the server root are
   rejected with HTTP 400.
4. Logs are stored at `<notebook dir>/.nbtrail/<notebook name>.jsonl`.

## 6. Verification

`nbtrail verify LOG` walks the file and, for every line, checks:
valid JSON → `seq` equals line index → `prev` equals the previous `hash` →
recomputed hash equals `hash`. It reports the **first** bad line and why.

## 7. Roadmap

- **v0.1** recorder, sealed log, `verify`, `report` (text/JSON)
- **v0.2** merge consecutive keystrokes into one `edit`; replay side panel with timeline slider and error/paste markers;
  HTML process card
- **v0.3** anchoring: server periodically signs the chain head (or JupyterHub
  stores it) so cutting or rebuilding the log is detectable
- **later** instructor batch reports; traceback-coach integration
