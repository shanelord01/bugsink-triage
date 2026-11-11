---
name: bugsink-triage
description: Use when working with a self-hosted Bugsink error tracker, for example "check bugsink", "what's open in Bugsink", "triage the new errors", "why is this issue happening", after a deploy, or when asked to comment on, resolve or mute a Bugsink issue. Lists open issues, traces each to a cause, classifies it, reports, and acts only on the user's yes. Read only by default and never deletes.
---

# Bugsink triage

Bugsink is a self-hosted, Sentry-compatible error tracker. This skill finds what is open, works out why,
tells the user, and changes an issue only when they agree.

Scripts live in `${CLAUDE_PLUGIN_ROOT}/skills/bugsink-triage/scripts/` and need only Python 3.9 or later.
API details, traps and unreadable-trace notes are in
`${CLAUDE_PLUGIN_ROOT}/skills/bugsink-triage/references/api.md`.

## Step 0: configuration

The scripts read the environment. Check it before anything else:

```bash
test -n "$BUGSINK_URL" && echo "url set" ; test -n "$BUGSINK_TOKEN$BUGSINK_TRIAGE_TOKEN" && echo "token set"
curl -s -o /dev/null -w '%{http_code}\n' "$BUGSINK_URL/accounts/login/"
```

- `BUGSINK_URL`: the server's base URL, no trailing path.
- `BUGSINK_TOKEN`: a token that can read projects, issues and events. Used for every read.
- `BUGSINK_TRIAGE_TOKEN`: a token that can also comment and triage. Used only by `act.py`.
- `BUGSINK_TAGS`: optional comma list of event tags to print (default `environment,release,request.id,component`).

A `200` from the login page means the server is reachable. A timeout or DNS failure means a VPN or tunnel is
down, so tell the user and stop. If a variable is missing, tell the user which one and how to make a token
(Bugsink, Tokens menu, choose the capabilities; see the README). Never print, log, commit or paste a token,
and never ask the user to paste one into the chat.

## Check: what is open

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/bugsink-triage/scripts/check.py"                    # last 24 hours
python3 "${CLAUDE_PLUGIN_ROOT}/skills/bugsink-triage/scripts/check.py" --since 2030-01-02T07:28:00Z
python3 "${CLAUDE_PLUGIN_ROOT}/skills/bugsink-triage/scripts/check.py" --all --project my-project
```

It lists the unresolved issues in every project (or those named with `--project`, by slug, name or id) whose
last event falls in the window, marks each NEW (first seen in the window) or recurring, and prints the latest
event: release, level, your chosen tags, device and the top of the trace. For a post-deploy check, use the time
the deploy began, not when it ended, so a failure during a rolling deploy is included.

Report every check, including an empty one ("no new issues in any project since 07:28 UTC").

## Triage: find the cause of each issue

Do not guess a cause from the title. For each open issue, work through these and write down what you found.

1. **Which build and who.** The event's `release` names the build. A build that is not the newest can still
   matter if users are still on it. Check whether the event came from your own testing.
2. **Did the request reach your servers?** If the event carries a request id tag and the user has server or
   proxy logs, look the id up. No line anywhere means the request failed before your servers: the client's
   network, a test lab, a load balancer. `examples/find-request-in-logs.sh` shows one way over SSH; adapt it to
   the user's setup and ask before connecting to any host.
3. **What the backend did.** With the time and node from step 2, read the application log around that moment.
4. **Unreadable frames.** Obfuscated or minified frames need a source map or mapping file. See the API reference.
5. **Read the code that reported it.** The top in-app frame names the reporter. Some reports are warnings by
   design and a comment above the call says why. Read the code before calling anything a bug.
6. **Search the user's own notes.** Search their docs, runbooks, tickets or memory tools for the message and
   the friendly id. An issue may already be explained, parked or waiting on someone else.
7. **Classify it** as exactly one of:
   - **bug**: your code is wrong. Explain the finding before fixing it.
   - **regression**: a resolved issue has new events. Bugsink reopens it. Find which release brought it back.
   - **expected**: the report exists to say something happened, such as a retry that then succeeded.
   - **outside**: the cause is not yours: a third-party service down, a pre-launch test lab, a user's network.
   - **parked**: known, and the user decided to leave it. Name where that decision is written down.

Say what you could not confirm. A missing tag that you needed is a gap in the reporter, and the report should
say so.

## Report to the user

For each issue give, in plain words: what happened and to whom (with the friendly id), the cause and the
evidence (the log line, the request, the code), its class, whether anyone was stopped from doing something,
and what you propose: a fix to explain first, a resolve with the reason, or leave it open. Lead with the answer.

## Act on an issue

Reads are free. **Every write needs the user's explicit yes for that issue.** Use `act.py`, which prints what
it would send and does nothing until you add `--yes`:

```bash
A="python3 ${CLAUDE_PLUGIN_ROOT}/skills/bugsink-triage/scripts/act.py"
$A comment <issue-uuid> "Cause: ... Evidence: ... Action: ..."
$A resolve <issue-uuid> --comment "Fixed in <commit> / <release>, shipped <date>, verified by <how>." --yes
$A mute-until <issue-uuid> --period hour --count 1 --threshold 10 --yes
$A reopen <issue-uuid> --yes
```

- **Resolve** once the cause is fixed and the fix has reached the users who can hit it, or once the issue is
  shown to be expected or outside. Always with a comment that says what it was, the evidence, and what was done.
  A resolved issue reopens when a new event arrives, which is how a regression shows up.
- **Mute** only when the user agrees, for something expected that would otherwise repeat. Prefer `mute-until`
  with a threshold so a flood still wakes it. A muted issue stays quiet when it recurs, so it can hide a real
  problem. Bugsink refuses to mute a resolved issue; reopen it first.
- **Leave open** anything waiting on a fix or a decision.
- **Never delete.** `act.py` has no delete action. If the user wants an issue deleted, tell them to do it in
  the Bugsink UI, because it is permanent.

After any change, say which issues you changed and how.

## Triage board (optional)

The board shows all open issues on one page with a verdict, a cause, a next step and choices per issue. It
needs the Artifact tool and the `db` capability, which exist only in Claude Code connected to claude.ai. If
they are not available, skip this section: everything above works without it.

1. Write `verdicts.json` keyed by friendly id, with `verdict` (bug, regression, expected, outside, parked),
   `group`, `cause`, `action`, `owner` and optionally `options`. The header of `scripts/board.py` lists the
   fields, including the optional `_work` (fix steps, their dependencies and PRs) and `_meta`.
2. Run `python3 "${CLAUDE_PLUGIN_ROOT}/skills/bugsink-triage/scripts/board.py" --verdicts verdicts.json --out board.html`.
3. Publish `board.html` with the Artifact tool, with `capabilities: {"db": {}}` the first time. Keep the
   artifact URL so a republish keeps the same link.
4. When the user says they have submitted, read the saved choices with ArtifactData (action `list`, collection
   `decisions`). Act only on the choices they made, through `act.py`, and name each resolve in your reply.

The page is a snapshot, so rebuild it after any resolve. It holds issue ids, device models and error text and
never a token. Check the error text for anything private before publishing.
