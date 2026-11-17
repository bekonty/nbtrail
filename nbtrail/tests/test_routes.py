import json

import pytest
from tornado.httpclient import HTTPClientError

from nbtrail.log import verify


def post(jp_fetch, body):
    return jp_fetch("nbtrail", "events", method="POST", body=json.dumps(body))


async def test_events_are_sealed_on_disk(jp_fetch, jp_root_dir):
    events = [{"kind": "session", "ts": 1, "action": "start"}, {"kind": "run", "ts": 2, "cell": "c", "ok": True}]
    r = await post(jp_fetch, {"notebook": "hw/a.ipynb", "events": events})
    assert r.code == 200 and json.loads(r.body)["appended"] == 2
    log = jp_root_dir / "hw" / ".nbtrail" / "a.ipynb.jsonl"
    assert verify(log).ok and verify(log).events == 2

    status = await jp_fetch("nbtrail", "status", params={"notebook": "hw/a.ipynb"})
    assert json.loads(status.body) == {"exists": True, "ok": True, "events": 2, "reason": ""}


@pytest.mark.parametrize(
    "body",
    [
        {"notebook": "../escape.ipynb", "events": [{"kind": "run", "ts": 1}]},
        {"notebook": "notes.txt", "events": [{"kind": "run", "ts": 1}]},
        {"notebook": "a.ipynb", "events": []},
        {"notebook": "a.ipynb", "events": [{"kind": "evil", "ts": 1}]},
    ],
)
async def test_bad_requests_rejected(jp_fetch, body):
    with pytest.raises(HTTPClientError) as e:
        await post(jp_fetch, body)
    assert e.value.code == 400


async def test_status_without_log(jp_fetch):
    r = await jp_fetch("nbtrail", "status", params={"notebook": "none.ipynb"})
    assert json.loads(r.body) == {"exists": False}
