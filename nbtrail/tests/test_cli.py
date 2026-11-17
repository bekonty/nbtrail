import json

from nbtrail.cli import main
from nbtrail.log import TrailLog, log_path_for


def make(tmp_path):
    nb = tmp_path / "hw.ipynb"
    log = TrailLog(log_path_for(nb))
    log.append(
        [
            {"kind": "snapshot", "ts": 0, "cells": [{"id": "a", "type": "code", "source": ""}]},
            {"kind": "edit", "ts": 1000, "cell": "a", "delta": [{"insert": "1/0"}]},
            {"kind": "run", "ts": 2000, "cell": "a", "ok": False, "error": "ZeroDivisionError"},
        ]
    )
    return nb, log


def test_verify_ok(tmp_path, capsys):
    nb, _ = make(tmp_path)
    assert main(["verify", str(nb)]) == 0
    assert "OK  3 events" in capsys.readouterr().out


def test_verify_fail(tmp_path, capsys):
    nb, log = make(tmp_path)
    log.path.write_text(log.path.read_text().replace("ZeroDivisionError", "NoError"))
    assert main(["verify", str(nb)]) == 1
    assert "FAIL  line 3" in capsys.readouterr().out


def test_report_json(tmp_path, capsys):
    nb, _ = make(tmp_path)
    assert main(["report", str(nb), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["verified"] and data["failed_runs"] == 1 and data["chars_typed"] == 3


def test_report_text(tmp_path, capsys):
    nb, _ = make(tmp_path)
    main(["report", str(nb)])
    out = capsys.readouterr().out
    assert "ZeroDivisionError×1" in out and "chain            intact" in out
