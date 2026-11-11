#!/usr/bin/env python3
"""Change the state of one Bugsink issue: comment, resolve, reopen, mute, unmute.

Usage:
  act.py comment   <issue-uuid> "text"                 [--yes]
  act.py resolve   <issue-uuid> --comment "why"        [--yes]
  act.py reopen    <issue-uuid>                        [--yes]
  act.py mute      <issue-uuid>                        [--yes]
  act.py mute-for  <issue-uuid> --period day --count 3 [--yes]
  act.py mute-until <issue-uuid> --period hour --count 1 --threshold 10 [--yes]
  act.py unmute    <issue-uuid>                        [--yes]

Without --yes it only prints what it would send. Ask the user first, then run it with --yes.
This script has no delete action on purpose. Needs BUGSINK_URL and BUGSINK_TRIAGE_TOKEN.

Bugsink answers 400 when you mute a resolved issue, so reopen it first.
A resolved issue re-opens by itself when a new event arrives; a muted one does not.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bugsink as bs  # noqa: E402

PERIODS = ("year", "month", "week", "day", "hour", "minute")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["comment", "resolve", "reopen", "mute", "mute-for", "mute-until", "unmute"])
    ap.add_argument("issue", help="issue uuid (the `id` check.py prints, not the friendly id)")
    ap.add_argument("text", nargs="?", help="comment text (for the comment action)")
    ap.add_argument("--comment", help="comment to post first (resolve, mute actions)")
    ap.add_argument("--period", choices=PERIODS, help="for mute-for and mute-until")
    ap.add_argument("--count", type=int, help="number of periods, for mute-for and mute-until")
    ap.add_argument("--threshold", type=int, help="event count that wakes a mute-until")
    ap.add_argument("--yes", action="store_true", help="actually send; without it nothing changes")
    a = ap.parse_args()

    steps = []  # (path, body)
    note = a.text if a.action == "comment" else a.comment
    if a.action == "comment" and not a.text:
        sys.exit("comment needs the text as the third argument.")
    if note:
        steps.append(("/issue-comments/", {"issue": a.issue, "comment": note}))
    if a.action != "comment":
        body: dict = {}
        if a.action in ("mute-for", "mute-until"):
            if not (a.period and a.count):
                sys.exit(f"{a.action} needs --period and --count.")
            body = {"period_name": a.period, "nr_of_periods": a.count}
            if a.action == "mute-until":
                if not a.threshold:
                    sys.exit("mute-until needs --threshold.")
                body["gte_threshold"] = a.threshold
        steps.append((f"/issues/{a.issue}/{a.action}/", body))

    for path, body in steps:
        print(f"{'POST' if a.yes else 'would POST'} {path} {body}")
    if not a.yes:
        print("Nothing sent. Add --yes after the user has agreed.")
        return
    tok = bs.write_token()
    for path, body in steps:
        bs.post(path, tok, body)
    if a.action != "comment":
        issue = bs.get(f"{bs.base_url()}/issues/{a.issue}/", tok)
        print(f"Now: {issue.get('friendly_id')} is_resolved={issue.get('is_resolved')} is_muted={issue.get('is_muted')}")
    else:
        print("Comment posted.")


if __name__ == "__main__":
    main()
