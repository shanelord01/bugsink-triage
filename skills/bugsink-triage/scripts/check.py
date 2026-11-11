#!/usr/bin/env python3
"""List open Bugsink issues seen in a window, with what triage needs. Read only.

Usage:
  check.py                          # unresolved issues seen in the last 24 hours, all projects
  check.py --since 2026-01-15T07:28:00Z
  check.py --hours 6 --project web --project api
  check.py --all                    # every unresolved issue, whenever last seen

For each issue it prints the friendly id, whether it is new in the window (first seen inside it)
or recurring, the event count, and the latest event: release, level, the tags you chose, the
device and the top of the stack trace.

Environment: BUGSINK_URL, BUGSINK_TOKEN, optional BUGSINK_TAGS (see bugsink.py).
The API ignores the is_resolved query filter, so this script filters on each issue itself.
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bugsink as bs  # noqa: E402


def summarise(ev: dict) -> list[str]:
    d = ev.get("data") or {}
    tags = bs.event_tags(ev)
    ctx = d.get("contexts") or {}
    os_, app, device = ctx.get("os") or {}, ctx.get("app") or {}, ctx.get("device") or {}
    out = [
        f"    latest {ev.get('timestamp')}  release {d.get('release')}  level {d.get('level')}",
        f"    message {str(bs.event_message(d))[:200]}",
    ]
    picked = {k: tags[k] for k in bs.tags_to_show() if k in tags}
    if picked:
        out.append("    tags " + "  ".join(f"{k}={v}" for k, v in picked.items()))
    where = " ".join(str(x).strip() for x in filter(None, [
        os_.get("name"), os_.get("version"), device.get("model"),
        app.get("app_version") and f"app {app.get('app_version')} ({app.get('app_build')})"]))
    if where:
        out.append(f"    device {where}")
    frames = bs.trace_head(ev)
    if frames:
        out.append("    trace " + " | ".join(frames))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--since", help="ISO time in UTC, e.g. 2026-01-15T07:28:00Z")
    ap.add_argument("--hours", type=float, default=24, help="window when --since is not given (default 24)")
    ap.add_argument("--all", action="store_true", help="every unresolved issue, no window")
    ap.add_argument("--project", action="append", help="project slug, name or id; repeatable; default all")
    a = ap.parse_args()

    since = None
    if not a.all:
        since = a.since or (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=a.hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    tok = bs.read_token()
    print(f"Bugsink: unresolved issues {'(all)' if a.all else f'seen since {since}'}")
    total = 0
    for p in bs.pick_projects(bs.projects(tok), a.project):
        found = list(bs.issues(p["id"], since, tok))
        total += len(found)
        print(f"\n{p.get('slug') or p.get('name')}: {len(found)}")
        for i in found:
            state = "NEW" if since and i["first_seen"] >= since else "recurring"
            muted = "  MUTED" if i.get("is_muted") else ""
            print(f"  {i['friendly_id']}  {state}{muted}  events {i['digested_event_count']}  "
                  f"first {i['first_seen'][:19]}Z  last {i['last_seen'][:19]}Z  id {i['id']}")
            print(f"    {(i.get('calculated_type') or '')}: {(i.get('calculated_value') or '')[:160]}")
            ev = bs.latest_event(i["id"], tok)
            if ev:
                print("\n".join(summarise(ev)))
    print(f"\nTotal: {total}")


if __name__ == "__main__":
    main()
