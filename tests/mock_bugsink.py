"""A tiny fake Bugsink API with synthetic data, for the tests. Not a real server."""
import copy
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

TOKEN = "test-token-0000"
PROJECTS = [
    {"id": 1, "name": "Demo web", "slug": "demo-web"},
    {"id": 2, "name": "Demo api", "slug": "demo-api"},
]
ISSUES = {
    1: [
        {"id": "aaaaaaaa-0000-0000-0000-000000000001", "friendly_id": "DEMO-WEB-1", "is_resolved": False, "is_muted": False,
         "digested_event_count": 7, "first_seen": "2030-01-02T03:00:00Z", "last_seen": "2030-01-02T09:00:00Z",
         "calculated_type": "TypeError", "calculated_value": "Cannot read properties of undefined (reading 'total')"},
        {"id": "aaaaaaaa-0000-0000-0000-000000000002", "friendly_id": "DEMO-WEB-2", "is_resolved": True, "is_muted": False,
         "digested_event_count": 3, "first_seen": "2030-01-01T03:00:00Z", "last_seen": "2030-01-02T08:00:00Z",
         "calculated_type": "RangeError", "calculated_value": "already resolved, must not be listed"},
    ],
    2: [
        {"id": "bbbbbbbb-0000-0000-0000-000000000001", "friendly_id": "DEMO-API-1", "is_resolved": False, "is_muted": True,
         "digested_event_count": 40, "first_seen": "2029-12-01T03:00:00Z", "last_seen": "2030-01-02T07:00:00Z",
         "calculated_type": "TimeoutError", "calculated_value": "upstream did not answer in 10s"},
    ],
}
_PRISTINE = copy.deepcopy(ISSUES)


def reset():
    """Restore the issues and forget recorded POSTs; tests that resolve things call this first."""
    for k, v in copy.deepcopy(_PRISTINE).items():
        ISSUES[k][:] = v
    Handler.posts.clear()


EVENTS = {
    "aaaaaaaa-0000-0000-0000-000000000001": {
        "id": "eeeeeeee-0000-0000-0000-000000000001", "timestamp": "2030-01-02T09:00:00Z",
        "data": {"release": "web@2.4.0", "level": "error",
                 "tags": {"environment": "production", "request.id": "req-demo-1", "component": "checkout", "secret.tag": "hidden"},
                 "contexts": {"os": {"name": "Linux", "version": "6.1"}, "device": {"model": "Demo Phone 1"}},
                 "exception": {"values": [{"type": "TypeError", "value": "Cannot read properties of undefined (reading 'total')"}]}},
        "stacktrace_md": "# TypeError\nCannot read properties of undefined\n### src/cart.js:42 in `sumTotal`\n    return cart.total\n### src/app.js:10 in `render`\n",
    },
    "bbbbbbbb-0000-0000-0000-000000000001": {
        "id": "eeeeeeee-0000-0000-0000-000000000002", "timestamp": "2030-01-02T07:00:00Z",
        "data": {"release": "api@1.9.3", "level": "warning", "tags": [["component", "billing"]],
                 "message": "upstream did not answer in 10s"},
        "stacktrace_md": "",
    },
}


class Handler(BaseHTTPRequestHandler):
    posts: list = []

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authed(self):
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self._send(401, {"detail": "bad token"})
            return False
        return True

    def do_GET(self):
        if not self._authed():
            return
        u = urlparse(self.path)
        q = parse_qs(u.query)
        path = u.path.replace("/api/canonical/0", "")
        if path == "/projects/":
            return self._send(200, {"next": None, "previous": None, "results": PROJECTS})
        if path == "/issues/":
            if "project" not in q:
                return self._send(400, {"project": ["This field is required."]})
            # Like the real server, ignore is_resolved and return everything.
            rows = sorted(ISSUES.get(int(q["project"][0]), []), key=lambda i: i["last_seen"], reverse=True)
            return self._send(200, {"next": None, "previous": None, "results": rows})
        m = re.fullmatch(r"/issues/([^/]+)/", path)
        if m:
            for rows in ISSUES.values():
                for i in rows:
                    if i["id"] == m.group(1):
                        return self._send(200, i)
            return self._send(404, {})
        if path == "/events/":
            e = EVENTS.get(q.get("issue", [""])[0])
            return self._send(200, {"next": None, "results": [{"id": e["id"]}] if e else []})
        m = re.fullmatch(r"/events/([^/]+)/", path)
        if m:
            for e in EVENTS.values():
                if e["id"] == m.group(1):
                    return self._send(200, e)
        self._send(404, {"detail": "not found"})

    def do_POST(self):
        if not self._authed():
            return
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        path = urlparse(self.path).path.replace("/api/canonical/0", "")
        Handler.posts.append((path, body))
        m = re.fullmatch(r"/issues/([^/]+)/resolve/", path)
        if m:
            for rows in ISSUES.values():
                for i in rows:
                    if i["id"] == m.group(1):
                        i["is_resolved"] = True
        self._send(200, {})


def serve():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"
