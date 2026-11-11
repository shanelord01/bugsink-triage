"""Small Bugsink API client shared by check.py, board.py, act.py and handoff.py. Standard library only.

Configuration comes from the environment first, then from an optional config file (see
bugsink-triage.config.example.json and the README, "Adapting it to your environment"):

  BUGSINK_URL           base URL of the server, e.g. https://bugsink.example.com
  BUGSINK_TOKEN         read token (falls back to BUGSINK_TRIAGE_TOKEN when unset)
  BUGSINK_TRIAGE_TOKEN  token allowed to comment, resolve and mute (only act.py uses it for writes)
  BUGSINK_TAGS          comma separated event tags to show (default below)
  BUGSINK_BOARD_DIR     state directory (default ~/.local/state/bugsink-triage-board)
  BUGSINK_TRIAGE_CONFIG path of the config file (default <state dir>/bugsink-triage.config.json)

The config file can rename those variables, read a token from a command instead, and set the
defaults for projects, tags, repos, PR owners and hand-off timing. Tokens are never printed.
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_TAGS = "environment,release,request.id,component"
CONFIG_NAME = "bugsink-triage.config.json"


def default_state_dir() -> Path:
    return Path(os.environ.get("BUGSINK_BOARD_DIR") or Path.home() / ".local/state/bugsink-triage-board").expanduser()


def config_path() -> Path:
    env = os.environ.get("BUGSINK_TRIAGE_CONFIG")
    return Path(env).expanduser() if env else default_state_dir() / CONFIG_NAME


_CONFIG: dict | None = None


def config() -> dict:
    """The user's config file, or {} when there is none. Keys starting with _ are dropped."""
    global _CONFIG
    if _CONFIG is None:
        path = config_path()
        _CONFIG = {}
        if path.exists():
            try:
                raw = json.loads(path.read_text())
            except ValueError as e:
                sys.exit(f"{path} is not valid JSON: {e}")
            if not isinstance(raw, dict):
                sys.exit(f"{path} must hold a JSON object.")
            _CONFIG = {k: v for k, v in raw.items() if not k.startswith("_")}
    return _CONFIG


def state_dir() -> Path:
    """Where verdicts.json, current.json and the rest live. The config file itself stays where
    BUGSINK_TRIAGE_CONFIG or the default state directory says, so it can always be found."""
    if os.environ.get("BUGSINK_BOARD_DIR"):
        return default_state_dir()
    custom = config().get("stateDir")
    return Path(custom).expanduser() if custom else default_state_dir()


def _from_command(argv) -> str:
    if not (isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv)):
        return ""
    try:  # argv list, no shell; the output is the token and is never printed
        return subprocess.run(argv, capture_output=True, text=True, check=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def base_url() -> str:
    cfg = config()
    url = (os.environ.get(cfg.get("urlEnv") or "BUGSINK_URL") or cfg.get("baseUrl") or "").strip().rstrip("/")
    if not url:
        sys.exit("The Bugsink URL is not set. Export BUGSINK_URL (e.g. https://bugsink.example.com) or set baseUrl in the config file.")
    return url + "/api/canonical/0"


def tags_to_show() -> tuple:
    cfg = config().get("tags")
    raw = os.environ.get("BUGSINK_TAGS") or (",".join(cfg) if isinstance(cfg, list) else "") or DEFAULT_TAGS
    return tuple(t.strip() for t in raw.split(",") if t.strip())


def default_projects() -> list[str]:
    p = config().get("projects")
    return [str(x) for x in p] if isinstance(p, list) else []


def read_token() -> str:
    cfg = config()
    t = (os.environ.get(cfg.get("readTokenEnv") or "BUGSINK_TOKEN")
         or os.environ.get(cfg.get("writeTokenEnv") or "BUGSINK_TRIAGE_TOKEN") or "").strip()
    t = t or _from_command(cfg.get("readTokenCommand")) or _from_command(cfg.get("writeTokenCommand"))
    if not t:
        sys.exit("No token: export BUGSINK_TOKEN (read) or BUGSINK_TRIAGE_TOKEN (read and write), or set a token command in the config file.")
    return t


def write_token() -> str:
    cfg = config()
    t = (os.environ.get(cfg.get("writeTokenEnv") or "BUGSINK_TRIAGE_TOKEN") or "").strip() or _from_command(cfg.get("writeTokenCommand"))
    if not t:
        sys.exit("No write token: export BUGSINK_TRIAGE_TOKEN (needs issues:comment and issues:triage), or set writeTokenCommand in the config file.")
    return t


def _request(method: str, url: str, tok: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Authorization": f"Bearer {tok}", "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        sys.exit(f"Bugsink answered {e.code} for {method} {url.split('?')[0]}: {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"Bugsink did not answer {url.split('?')[0]}: {e.reason}. Is the server reachable from here (VPN, tunnel)?")


def get(url: str, tok: str):
    return _request("GET", url, tok)


def post(path: str, tok: str, body: dict):
    return _request("POST", f"{base_url()}{path}", tok, body)


def pages(url: str, tok: str):
    """Yield every item of a paginated list, following the response's `next` URL."""
    while url:
        page = get(url, tok)
        if isinstance(page, list):
            yield from page
            return
        yield from page.get("results", [])
        url = page.get("next")


def projects(tok: str) -> list[dict]:
    return list(pages(f"{base_url()}/projects/", tok))


def pick_projects(all_projects: list[dict], wanted: list[str] | None) -> list[dict]:
    """Match --project values against slug, name or id. No values means every project."""
    wanted = wanted or default_projects()
    if not wanted:
        return all_projects
    out = []
    for w in wanted:
        hit = [p for p in all_projects if w in (str(p.get("id")), p.get("slug"), p.get("name"))]
        if not hit:
            known = ", ".join(str(p.get("slug") or p.get("name")) for p in all_projects)
            sys.exit(f"No project matches '{w}'. Known projects: {known}")
        out.extend(h for h in hit if h not in out)
    return out


def issues(project_id, since: str | None, tok: str):
    """Unresolved issues, newest last_seen first, stopping at the window's edge.

    The API ignores an is_resolved query filter (seen on Bugsink 2.6.0), so this filters here.
    """
    url = f"{base_url()}/issues/?project={project_id}&sort=last_seen&order=desc"
    while url:
        page = get(url, tok)
        for i in page.get("results", []):
            if since and i["last_seen"] < since:
                return
            if not i.get("is_resolved"):
                yield i
        url = page.get("next")


def latest_event(issue_id: str, tok: str):
    page = get(f"{base_url()}/events/?issue={issue_id}&order=desc", tok)
    first = (page.get("results") or [None])[0]
    return get(f"{base_url()}/events/{first['id']}/", tok) if first else None


def event_tags(ev: dict) -> dict:
    tags = ((ev or {}).get("data") or {}).get("tags") or {}
    if isinstance(tags, list):  # some SDKs send [[key, value], ...]
        tags = {k: v for k, v in tags}
    return tags


def event_message(d: dict) -> str | None:
    msg = (d.get("logentry") or {}).get("formatted") or d.get("message")
    if isinstance(msg, dict):
        msg = msg.get("formatted") or msg.get("message")
    for x in (d.get("exception") or {}).get("values", []) or []:
        msg = msg or f"{x.get('type')}: {x.get('value')}"
    return msg


def trace_head(ev: dict, n: int = 4) -> list[str]:
    """Headings of the Markdown stack trace: one line per frame. The format may change between
    Bugsink versions, so this keeps only the heading lines and does not parse further."""
    st = ((ev or {}).get("stacktrace_md") or "").strip().splitlines()
    return [l.lstrip("# ").strip()[:110] for l in st if l.startswith("#")][:n]
