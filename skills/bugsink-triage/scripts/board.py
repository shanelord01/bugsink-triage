"""Build a triage board (one self-contained HTML page) from the open Bugsink issues. Read only.

Usage:
  board.py --verdicts verdicts.json --out board.html
  board.py --prs-only                  # only GitHub: re-read the PRs the last build knows (no Bugsink)
  board.py --project web --project api

Reads every unresolved issue (the same data as check.py --all) and joins it to the verdicts your
triage wrote. The page shows one card per issue: project, latest build, event count, last seen,
the error, the top of the trace, a link to the issue in Bugsink, the verdict and the next step.
Issues that share a cause are grouped under one heading.

verdicts.json maps a friendly id to what triage decided. Every key is optional:

  {
    "WEB-25": {
      "verdict": "bug",              # bug | regression | expected | outside | parked | untriaged
      "group": "checkout timeout",
      "cause": "The payment call has no timeout, so a slow provider hangs the request.",
      "action": "Add a 10 second timeout and retry once.",
      "owner": "Payments team",
      "options": ["Fix it", "Leave open"],   # first is recommended
      "comment": "Optional. The comment posted if the user picks a resolve option. Without it the board suggests one from the cause."
    }
  }

Two reserved keys sit beside the issues. "_work" lists the fix steps behind the issues,
and drives the progress band, the waiting-to-land list and the "what blocks what" graph:

  "_work": [{"code": "W1", "name": "Payments PR 91", "short": "Payments PR 91",
             "state": "landing",            # todo | running | landing | landed
             "size": "M",                   # S | M | L, weights 1 | 2 | 3
             "deps": [], "fixes": ["WEB-25"],
             "links": [{"label": "PR 91", "url": "https://github.com/acme/payments/pull/91"}],
             "note": "waits on review"}]

"_meta" holds {"eyebrow": "...", "subtitle": "...", "needs": [...], "questions": ["..."], "repos": [...]},
the heading line and the two lists at the foot of the page. A "needs" entry is a string, or
{"text": "Merge PR 91", "url": "https://github.com/acme/payments/pull/91"}: the page links it, and when
the link is a GitHub pull request the board reads its state with the gh CLI (open, draft, merged, and
CI) and drops the line once it merges. With "repos" in _meta (["owner/repo", ...]) the board also finds
open pull requests that mention an open issue's id in their title, body or branch, adds a "Merge ..."
line for each and links it on the issue's card. A work step whose links are all merged PRs shows as
landed. GitHub awareness is optional: it needs the gh CLI, and --no-prs skips it. With no "_work" the
band shows how many open issues are triaged.

Each card offers the options as a radio group, the first preselected as recommended; a default set per
verdict applies when "options" is absent. Picking a resolve option shows a comment box pre-filled with
the suggested comment. In claude.ai Artifacts with the `db` capability, the Submit button saves the
choices to the collection "decisions" (one document per submit); Claude reads them back with
ArtifactData, acts on them, then marks each document done. Anywhere else, "Copy as message" gives the
same choices as text for the chat.

The output is an HTML fragment (title, meta, style, body, script) that the Artifact tool wraps. It holds
issue ids, device models and error text, never a token. Besides board.html it writes current.json beside
it: the live copy of the data, to be written to the document board/current with ArtifactData. The page
paints from its embedded copy, then follows that document, so a data update needs no republish. Republish
only when the template changes.

State lives in $BUGSINK_BOARD_DIR (default ~/.local/state/bugsink-triage-board): verdicts.json,
artifact-url.txt (the board's Artifact link, so a republish keeps it), current.json, last-synced.json and
the built board.html.
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
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
PR_URL = re.compile(r"^https://github\.com/[\w.-]+/[\w.-]+/pull/\d+$")
VERDICTS = ("bug", "regression", "expected", "outside", "parked", "untriaged")


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
    server = bs.base_url().split("/api/")[0]
    rows = []
    for p in bs.pick_projects(bs.projects(tok), wanted):
        for i in bs.issues(p["id"], None, tok):
            rows.append({
                "id": i["friendly_id"],
                "url": f"{server}/issues/issue/{i['id']}/event/last/",
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


def pr_status(url: str) -> dict | None:
    """State of a GitHub pull request through the gh CLI, or None when gh cannot answer."""
    if not shutil.which("gh"):
        return None
    try:
        out = subprocess.run(["gh", "pr", "view", url, "--json", "state,isDraft,statusCheckRollup,mergeStateStatus"],
                             capture_output=True, text=True, timeout=30)
        if out.returncode:
            return None
        d = json.loads(out.stdout)
    except (subprocess.SubprocessError, ValueError):
        return None
    checks = [c.get("conclusion") or c.get("status") or "" for c in d.get("statusCheckRollup") or []]
    bad = any(c in ("FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE") for c in checks)
    wait = any(c in ("IN_PROGRESS", "QUEUED", "PENDING", "WAITING", "") for c in checks)
    return {"state": d.get("state", "").lower(), "draft": bool(d.get("isDraft")),
            "checks": "failing" if bad else "pending" if wait else "passing" if checks else "none"}


def discover_prs(rows: list, meta: dict) -> None:
    """Find open pull requests that mention an open issue's id, in the repos named by _meta.repos
    (for example ["owner/app", "owner/backend"]). Each becomes a "Merge ..." line under Needs you and a
    link on the issue's card, so a fix someone opens never has to be added by hand."""
    repos = meta.get("repos") or []
    if not repos or not shutil.which("gh"):
        return
    have = {n.get("url") for n in meta.get("needs") or [] if isinstance(n, dict)}
    found = []
    for repo in repos:
        try:
            out = subprocess.run(["gh", "pr", "list", "--repo", repo, "--state", "open", "--limit", "50",
                                  "--json", "number,title,url,body,headRefName"], capture_output=True, text=True, timeout=30)
            prs = json.loads(out.stdout) if out.returncode == 0 else []
        except (subprocess.SubprocessError, ValueError):
            prs = []
        for pr in prs:
            text = f"{pr['title']}\n{pr.get('body') or ''}\n{pr.get('headRefName') or ''}"
            hit = [r for r in rows if re.search(rf"(?<![\w-]){re.escape(r['id'])}(?![\w-])", text)]
            if not hit:
                continue
            for r in hit:
                r.setdefault("prs", []).append({"label": f"{repo.split('/')[1]} PR {pr['number']}", "url": pr["url"]})
            if pr["url"] not in have:
                found.append({"text": f"Merge {repo.split('/')[1]} PR {pr['number']}: {pr['title']}", "url": pr["url"]})
                have.add(pr["url"])
    if found:
        meta["needs"] = list(meta.get("needs") or []) + found


def enrich_prs(work: list, meta: dict) -> None:
    """Read every GitHub PR the board links, then follow it: a merged PR lands its step and drops
    its "needs you" line; the page shows the state and CI beside each link."""
    cache: dict[str, dict | None] = {}
    get = lambda u: cache.setdefault(u, pr_status(u) if PR_URL.match(u or "") else None)
    for w in work:
        links = w.get("links") or []
        for l in links:
            st = get(l.get("url", ""))
            if st:
                l["pr"] = st
        known = [l["pr"] for l in links if l.get("pr")]
        if known and len(known) == len(links) and all(p["state"] == "merged" for p in known):
            w["state"] = "landed"
        elif any(p["state"] == "open" for p in known) and w.get("state") in (None, "todo", "running"):
            w["state"] = "landing"
    needs = []
    for n in meta.get("needs") or []:
        if isinstance(n, dict) and n.get("url"):
            st = get(n["url"])
            if st and st["state"] in ("merged", "closed"):
                continue  # done: nothing left for the user
            if st:
                n["pr"] = st
        needs.append(n)
    if "needs" in meta:
        meta["needs"] = needs


def suggested_comment(r: dict) -> str:
    """The comment Claude proposes when the user picks "Resolve with a comment": the cause when
    triage recorded one, the class, and the re-open note. The user can edit it on the board."""
    cause = (r.get("cause") or "").strip()
    head = f"{r['id']}: {cause}" if cause else f"{r['id']}: triaged as {r['verdict']}."
    if cause and not cause.endswith("."):
        head += "."
    return f"{head} Resolved in the {f"{dt.date.today().day} {dt.date.today():%b %Y}"} triage. It re-opens if it recurs."


def refresh_prs_only() -> None:
    """Re-read GitHub for the PRs the board already knows, and for new PRs that mention an open
    issue, without touching Bugsink. Works on the last build (current.json), so it is cheap enough
    to run every few minutes. Prints "changed" or "no change" against last-synced.json."""
    cur = STATE / "current.json"
    if not cur.exists():
        sys.exit("No current.json yet: run board.py once first.")
    data = json.loads(cur.read_text())
    rows, work, meta = data["issues"], data.get("work") or [], data.get("meta") or {}
    for r in rows:
        r["prs"] = []  # rediscovered below, so a PR is never listed twice
    discover_prs(rows, meta)
    enrich_prs(work, meta)
    data.update(issues=rows, work=work, meta=meta)
    cur.write_text(json.dumps(data))
    synced = STATE / "last-synced.json"
    strip = lambda d: {k: v for k, v in d.items() if k != "generated"}
    same = synced.exists() and strip(json.loads(synced.read_text())) == strip(data)
    print("no change" if same else "changed")


def main() -> None:
    if "--prs-only" in sys.argv:
        refresh_prs_only()
        return
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--verdicts", help=f"JSON file of triage verdicts keyed by friendly id (default {STATE}/verdicts.json)")
    ap.add_argument("--out", help=f"HTML file to write (default {STATE}/board.html)")
    ap.add_argument("--project", action="append", help="project slug, name or id; repeatable; default all")
    ap.add_argument("--no-prs", action="store_true", help="do not ask GitHub about linked pull requests")
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
        r["comment"] = v.get("comment") or suggested_comment(r)
    work = verdicts.get("_work") or []
    meta = verdicts.get("_meta") or {}
    if not a.no_prs:
        discover_prs(rows, meta)
        enrich_prs(work, meta)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # A closing script tag inside the JSON would end the script element early.
    data = json.dumps({"generated": stamp, "issues": rows, "work": work, "meta": meta}).replace("</", "<\\/")
    out.write_text(PAGE.replace("__DATA__", data).replace("__STAMP__", html.escape(stamp)))
    # The same data as the document board/current in the page's database. Writing that document
    # (ArtifactData set, pinned with if_version) updates every open view without a republish.
    (out.parent / "current.json").write_text(json.dumps({"generated": stamp, "issues": rows, "work": work, "meta": meta}))
    print(f"Wrote {out}: {len(rows)} open issues, {sum(r['verdict'] == 'untriaged' for r in rows)} untriaged")


PAGE = (Path(__file__).resolve().parent / "board.template.html").read_text()

if __name__ == "__main__":
    main()
