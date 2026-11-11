#!/usr/bin/env python3
"""Build a triage board (one self-contained HTML page) from the open Bugsink issues. Read only.

Usage:
  board.py --verdicts verdicts.json --out board.html
  board.py --project web --project api

Reads every unresolved issue (the same data as check.py --all) and joins it to the verdicts your
triage wrote. The page shows one card per issue: project, latest build, event count, last seen,
the error, the top of the trace, the verdict and the next step. Issues that share a cause are
grouped under one heading.

verdicts.json maps a friendly id to what triage decided. Every key is optional:

  {
    "WEB-25": {
      "verdict": "bug",              # bug | regression | expected | outside | parked | untriaged
      "group": "checkout timeout",
      "cause": "The payment call has no timeout, so a slow provider hangs the request.",
      "action": "Add a 10 second timeout and retry once.",
      "owner": "Payments team",
      "options": ["Fix it", "Leave open"]   # first is recommended
    }
  }

Two reserved keys sit beside the issues. "_work" lists the fix steps behind the issues and drives
the progress band, the waiting-to-land list and the "what blocks what" graph:

  "_work": [{"code": "W1", "name": "Payments PR 91", "short": "Payments PR 91",
             "state": "landing",            # todo | running | landing | landed
             "size": "M",                   # S | M | L, weights 1 | 2 | 3
             "deps": [], "fixes": ["WEB-25"],
             "links": [{"label": "PR 91", "url": "https://example.com/pr/91"}], "note": "waits on review"}]

"_meta" holds {"eyebrow": "...", "subtitle": "...", "needs": ["..."], "questions": ["..."]}, the
heading line, and the two lists at the foot of the page. With no "_work" the band shows how many
open issues are triaged.

Each card offers the options as a radio group, the first preselected as recommended; a default set
per verdict applies when "options" is absent. In claude.ai Artifacts with the `db` capability, the
Submit button saves the choices to the collection "decisions"; Claude reads them back with
ArtifactData. Anywhere else, "Copy as message" gives the same choices as text for the chat.

The output is an HTML fragment (title, meta, style, body, script) that the Artifact tool wraps. It
holds issue ids, device models and error text, never a token. State lives in
$BUGSINK_BOARD_DIR (default ~/.local/state/bugsink-triage-board): verdicts.json, artifact-url.txt
and the built board.html.
"""
import argparse
import datetime as dt
import html
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bugsink as bs  # noqa: E402

DEFAULT_OPTIONS = {
    "bug": ["Fix it", "Leave open", "Resolve with a comment"],
    "regression": ["Fix it", "Leave open", "Resolve with a comment"],
    "expected": ["Resolve with a comment", "Leave open", "Mute it"],
    "outside": ["Resolve with a comment", "Leave open", "Mute it"],
    "parked": ["Leave parked", "Resolve with a comment", "Investigate now"],
    "untriaged": ["Investigate", "Leave open", "Resolve with a comment"],
}
STATE = Path(os.environ.get("BUGSINK_BOARD_DIR") or Path.home() / ".local/state/bugsink-triage-board")
VERDICTS = tuple(DEFAULT_OPTIONS)


def event_summary(ev: dict | None) -> dict:
    d = (ev or {}).get("data") or {}
    tags = bs.event_tags(ev or {})
    ctx = d.get("contexts") or {}
    os_, device = ctx.get("os") or {}, ctx.get("device") or {}
    return {
        "release": d.get("release") or "",
        "level": d.get("level") or "",
        "device": " ".join(str(x).strip() for x in filter(None, [os_.get("name"), os_.get("version"), device.get("model")])),
        "tags": {k: tags[k] for k in bs.tags_to_show() if k in tags},
        "trace": bs.trace_head(ev or {}),
    }


def collect(wanted: list[str] | None) -> list[dict]:
    tok = bs.read_token()
    rows = []
    for p in bs.pick_projects(bs.projects(tok), wanted):
        for i in bs.issues(p["id"], None, tok):
            rows.append({
                "id": i["friendly_id"],
                "project": p.get("slug") or p.get("name"),
                "events": i["digested_event_count"],
                "first": i["first_seen"][:19] + "Z",
                "last": i["last_seen"][:19] + "Z",
                "muted": bool(i.get("is_muted")),
                "type": i.get("calculated_type") or "",
                "value": (i.get("calculated_value") or "")[:240],
                **event_summary(bs.latest_event(i["id"], tok)),
            })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--verdicts", help=f"JSON file of triage verdicts keyed by friendly id (default {STATE}/verdicts.json)")
    ap.add_argument("--out", help=f"HTML file to write (default {STATE}/board.html)")
    ap.add_argument("--project", action="append", help="project slug, name or id; repeatable; default all")
    a = ap.parse_args()

    STATE.mkdir(parents=True, exist_ok=True)
    vpath = Path(a.verdicts) if a.verdicts else STATE / "verdicts.json"
    out = Path(a.out) if a.out else STATE / "board.html"
    verdicts = json.loads(vpath.read_text()) if vpath.exists() else {}
    rows = collect(a.project)
    for r in rows:
        v = verdicts.get(r["id"]) or {}
        r["verdict"] = v.get("verdict") if v.get("verdict") in VERDICTS else "untriaged"
        r["group"] = v.get("group", "")
        r["cause"] = v.get("cause", "")
        r["action"] = v.get("action", "")
        r["owner"] = v.get("owner", "")
        r["options"] = v.get("options") or DEFAULT_OPTIONS[r["verdict"]]
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # A closing script tag inside the JSON would end the script element early.
    data = json.dumps({"generated": stamp, "issues": rows, "work": verdicts.get("_work") or [],
                       "meta": verdicts.get("_meta") or {}}).replace("</", "<\\/")
    out.write_text(PAGE.replace("__DATA__", data).replace("__STAMP__", html.escape(stamp)))
    print(f"Wrote {out}: {len(rows)} open issues, {sum(r['verdict'] == 'untriaged' for r in rows)} untriaged")


PAGE = (Path(__file__).resolve().parent / "board.template.html").read_text()

if __name__ == "__main__":
    main()
