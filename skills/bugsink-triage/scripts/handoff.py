#!/usr/bin/env python3
"""Build a hand-off record for work given to another session, and the close-out line for its brief.

  handoff.py new --to-id ID --to-name NAME --task "what was asked" --step W1 --issues PROJ-1 PROJ-2 \\
                 [--hours 24] [--doc-id ho-checkout] [--artifact-url URL]

Prints JSON: {"doc_id", "document", "close_out"}. Write `document` to the board database with
ArtifactData `set` on collection `handoffs`, doc `doc_id`, and end your hand-off message with
`close_out`. Without the Artifact tool, keep the record in your report and skip the board part.

The due time defaults to `handoffDueHours` in the config (24). Pure data: this script sends nothing.
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bugsink as bs  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["new"])
    ap.add_argument("--to-id", required=True)
    ap.add_argument("--to-name", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--step", default="", help="the _work code this advances")
    ap.add_argument("--issues", nargs="*", default=[], help="friendly ids")
    ap.add_argument("--hours", type=float, help="hours until due (default handoffDueHours, else 24)")
    ap.add_argument("--doc-id", help="document id (default ho-<slug of the task>)")
    ap.add_argument("--artifact-url", help="default: the contents of artifact-url.txt in the state dir")
    a = ap.parse_args()

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    hours = a.hours if a.hours is not None else float(bs.config().get("handoffDueHours", 24))
    fmt = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")
    doc_id = a.doc_id or "ho-" + (re.sub(r"[^a-z0-9]+", "-", a.task.lower()).strip("-")[:32] or "task")
    url = a.artifact_url
    if not url:
        f = bs.state_dir() / "artifact-url.txt"
        url = f.read_text().strip() if f.exists() else "<the board's artifact URL>"
    doc = {"to": {"id": a.to_id, "name": a.to_name}, "task": a.task, "step": a.step, "issues": a.issues,
           "askedAt": fmt(now), "dueAt": fmt(now + dt.timedelta(hours=hours)), "status": "open"}
    close = (f"When done, send the evidence (PR link, release or update ids) back to the session that asked, then mark "
             f"the hand-off done: update document handoffs/{doc_id} on the board at {url} with status \"done\", "
             f"doneAt (ISO time) and evidence (one plain sentence).")
    print(json.dumps({"doc_id": doc_id, "document": doc, "close_out": close}, indent=2))


if __name__ == "__main__":
    main()
