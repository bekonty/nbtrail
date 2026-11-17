import json

import pytest

from nbtrail.log import GENESIS, InvalidEvent, TrailLog, compute_hash, log_path_for, verify


def ev(kind="run", ts=1000, **kw):
    base = {"kind": kind, "ts": ts}
    if kind in ("run", "edit", "paste"):
        base["cell"] = "c1"
    if kind == "run":
        base.setdefault("ok", True)
    return {**base, **kw}


@pytest.fixture
def log(tmp_path):
    return TrailLog(tmp_path / ".nbtrail" / "hw.ipynb.jsonl")


def lines(log):
    return log.path.read_text().splitlines()


def test_log_path_sits_next_to_notebook(tmp_path):
    assert log_path_for(tmp_path / "hw" / "a.ipynb") == tmp_path / "hw" / ".nbtrail" / "a.ipynb.jsonl"


def test_first_event_links_to_genesis_and_chain_continues(log):
    a, b = log.append([ev(ts=1), ev(ts=2)])
    assert a["prev"] == GENESIS and a["seq"] == 0
    assert b["prev"] == a["hash"] and b["seq"] == 1
    assert a["hash"] == compute_hash(a)


def test_chain_continues_across_instances(log):
    log.append([ev()])
    again = TrailLog(log.path)
    (c,) = again.append([ev(ts=5)])
    assert c["seq"] == 1
    assert verify(log.path).ok


def test_verify_ok(log):
    log.append([ev(ts=i) for i in range(10)])
    r = verify(log.path)
    assert r.ok and r.events == 10


def test_verify_detects_edited_content(log):
    log.append([ev(ts=i) for i in range(5)])
    rows = lines(log)
    tampered = json.loads(rows[2])
    tampered["ok"] = False  # pretend a run failed
    rows[2] = json.dumps(tampered)
    log.path.write_text("\n".join(rows) + "\n")
    r = verify(log.path)
    assert not r.ok and r.bad_line == 3 and "hash mismatch" in r.reason
    assert r.events == 2


def test_verify_detects_rehashed_line_via_chain(log):
    """Re-computing the edited line's own hash is not enough: the next line breaks."""
    log.append([ev(ts=i) for i in range(5)])
    rows = lines(log)
    tampered = json.loads(rows[2])
    tampered["ok"] = False
    tampered["hash"] = compute_hash(tampered)
    rows[2] = json.dumps(tampered)
    log.path.write_text("\n".join(rows) + "\n")
    r = verify(log.path)
    assert not r.ok and r.bad_line == 4 and "chain broken" in r.reason


def test_verify_detects_deleted_line(log):
    log.append([ev(ts=i) for i in range(5)])
    rows = lines(log)
    del rows[1]
    log.path.write_text("\n".join(rows) + "\n")
    r = verify(log.path)
    assert not r.ok and r.bad_line == 2 and "seq" in r.reason


def test_verify_detects_reordering(log):
    log.append([ev(ts=i) for i in range(4)])
    rows = lines(log)
    rows[1], rows[2] = rows[2], rows[1]
    log.path.write_text("\n".join(rows) + "\n")
    assert not verify(log.path).ok


def test_verify_detects_garbage(log):
    log.append([ev()])
    with log.path.open("a") as f:
        f.write("{not json\n")
    r = verify(log.path)
    assert not r.ok and r.reason == "not valid JSON"


@pytest.mark.parametrize(
    "bad",
    [
        "not a dict",
        {"kind": "teleport", "ts": 1},
        {"kind": "run", "ts": "yesterday"},
        {"kind": "run", "ts": 1, "hash": "f" * 64},
        {"kind": "run", "ts": 1, "seq": 99},
        {"kind": "edit", "ts": 1, "delta": [{"insert": "x" * 1_000_001}]},
    ],
)
def test_invalid_events_rejected(log, bad):
    with pytest.raises(InvalidEvent):
        log.append([bad])


def test_bad_event_rejects_whole_batch(log):
    with pytest.raises(InvalidEvent):
        log.append([ev(), {"kind": "nope", "ts": 1}])
    assert not log.path.exists()


def test_restarts_cleanly_if_log_deleted_while_cached(log):
    """Found in the end-to-end run: a deleted log must not continue from the old head."""
    log.append([ev(ts=1), ev(ts=2)])
    log.path.unlink()
    (first,) = log.append([ev(ts=3)])
    assert first["seq"] == 0 and first["prev"] == GENESIS
    assert verify(log.path).ok
