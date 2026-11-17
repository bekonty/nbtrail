import json
from pathlib import Path

import tornado
from jupyter_server.base.handlers import APIHandler
from jupyter_server.utils import url_path_join

from .log import InvalidEvent, TrailLog, log_path_for, verify

MAX_BATCH = 500


class _Base(APIHandler):
    def _notebook_path(self, rel: str) -> Path:
        """Resolve a notebook path inside the server root; refuse anything outside it."""
        root = Path(self.settings["server_root_dir"]).expanduser().resolve()
        if not rel or not rel.endswith(".ipynb"):
            raise tornado.web.HTTPError(400, "notebook must be a .ipynb path")
        nb = (root / rel).resolve()
        if root not in nb.parents:
            raise tornado.web.HTTPError(400, "notebook path is outside the server root")
        return nb

    def _log(self, nb: Path) -> TrailLog:
        logs = self.settings.setdefault("nbtrail_logs", {})
        path = log_path_for(nb)
        if path not in logs:
            logs[path] = TrailLog(path)
        return logs[path]


class EventsHandler(_Base):
    @tornado.web.authenticated
    def post(self):
        try:
            body = json.loads(self.request.body)
        except json.JSONDecodeError:
            raise tornado.web.HTTPError(400, "body must be JSON")
        events = body.get("events")
        if not isinstance(events, list) or not 0 < len(events) <= MAX_BATCH:
            raise tornado.web.HTTPError(400, f"events must be a list of 1..{MAX_BATCH}")
        nb = self._notebook_path(body.get("notebook", ""))
        try:
            sealed = self._log(nb).append(events)
        except InvalidEvent as e:
            raise tornado.web.HTTPError(400, str(e))
        self.finish(json.dumps({"appended": len(sealed), "head": sealed[-1]["hash"]}))


class StatusHandler(_Base):
    @tornado.web.authenticated
    def get(self):
        nb = self._notebook_path(self.get_argument("notebook", ""))
        path = log_path_for(nb)
        if not path.exists():
            self.finish(json.dumps({"exists": False}))
            return
        result = verify(path)
        self.finish(json.dumps({"exists": True, "ok": result.ok, "events": result.events, "reason": result.reason}))


def setup_route_handlers(web_app):
    base_url = web_app.settings["base_url"]
    web_app.add_handlers(
        ".*$",
        [
            (url_path_join(base_url, "nbtrail", "events"), EventsHandler),
            (url_path_join(base_url, "nbtrail", "status"), StatusHandler),
        ],
    )
