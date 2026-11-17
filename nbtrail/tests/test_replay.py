import pytest

from nbtrail.replay import apply_delta, state_at, summarize


@pytest.mark.parametrize(
    "text, delta, expected",
    [
        ("", [{"insert": "abc"}], "abc"),
        ("hello", [{"retain": 5}, {"insert": "!"}], "hello!"),
        ("hello", [{"delete": 1}, {"insert": "J"}], "Jello"),
        ("abcdef", [{"retain": 2}, {"delete": 2}], "abef"),
        ("x = 1", [], "x = 1"),
    ],
)
def test_apply_delta(text, delta, expected):
    assert apply_delta(text, delta) == expected


def seal(events):
    return [{"seq": i, **e} for i, e in enumerate(events)]


SESSION = seal(
    [
        {"kind": "snapshot", "ts": 0, "cells": [{"id": "a", "type": "code", "source": ""}]},
        {"kind": "edit", "ts": 60_000, "cell": "a", "delta": [{"insert": "print(x)"}]},
        {"kind": "run", "ts": 61_000, "cell": "a", "ok": False, "error": "NameError"},
        {"kind": "edit", "ts": 120_000, "cell": "a", "delta": [{"insert": "x = 1\n"}]},
        {"kind": "run", "ts": 121_000, "cell": "a", "ok": True, "error": None},
        {"kind": "paste", "ts": 2_000_000, "cell": "a", "chars": 4},
        {"kind": "edit", "ts": 2_000_001, "cell": "a", "delta": [{"retain": 14}, {"insert": "\n# a"}]},
    ]
)


def test_state_at_rebuilds_history():
    assert state_at(SESSION, upto=0)[0]["source"] == ""
    assert state_at(SESSION, upto=1)[0]["source"] == "print(x)"
    assert state_at(SESSION)[0]["source"] == "x = 1\nprint(x)\n# a"


def test_later_snapshot_resets_state():
    events = SESSION + seal([{"kind": "snapshot", "ts": 0, "cells": []}])
    events[-1]["seq"] = len(SESSION)
    assert state_at(events) == []


def test_summary():
    s = summarize(SESSION)
    assert s.runs == 2 and s.failed_runs == 1
    assert s.error_types == {"NameError": 1}
    assert s.error_fix_cycles == 1
    assert s.chars_typed == len("print(x)") + len("x = 1\n")
    assert s.chars_pasted == 4 and s.pastes == 1
    # 1 + 0.0167 + 0.983 + 0.0167 min; the 31-min gap before the paste is idle
    assert s.active_minutes == 2.0


def test_summary_of_empty_log():
    s = summarize([])
    assert s.events == 0 and s.typed_share == 1.0
