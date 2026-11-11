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

Everything specific to the user's environment lives in environment variables and one optional config file,
`bugsink-triage.config.json` in the state directory (default `~/.local/state/bugsink-triage-board/`, or the path in
`BUGSINK_TRIAGE_CONFIG`). Check what is set before anything else:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/bugsink-triage/scripts/config.py" show
```

It prints the server, how each token resolves (never the token), the projects, tags, repos, PR owners, hand-off
timing and style note. If something is missing, tell the user which setting and point them to the README section
"Adapting it to your environment". `config.py init` writes a commented example config. Then confirm the server
answers (`curl -s -o /dev/null -w '%{http_code}\n' "<server>/accounts/login/"`): `200` means it is reachable. A
timeout or DNS failure means a VPN or tunnel is down, so tell the user and stop.

- Server: `BUGSINK_URL` (or `baseUrl` in the config).
- Read token: `BUGSINK_TOKEN`, used for every read. Write token: `BUGSINK_TRIAGE_TOKEN`, used only by `act.py`.
  The config can rename these variables or give a command that prints the token.
- Tags to print per event: `BUGSINK_TAGS` or `tags` (default `environment,release,request.id,component`).
- `projects`, `repos`, `prSessions`, `handoffDueHours` and `styleNote` are described in the README.

Never print, log, commit or paste a token, and never ask the user to paste one into the chat. If the config has a
`styleNote`, follow it when you word reports, comments and hand-off briefs.

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

The board shows all open issues on one page: a progress band, a waiting-to-land list, a hover-traced
dependency graph of the fix steps behind the issues, and one card per issue with its verdict, cause, next
step, a link to the issue in Bugsink and choices for the user. It needs the Artifact tool and the `db`
capability, which exist only in Claude Code connected to claude.ai. If they are not available, skip this
section: everything above works without it.

State lives in `$BUGSINK_BOARD_DIR` (or `stateDir` in the config; default `~/.local/state/bugsink-triage-board`): `verdicts.json` (merge each
triage's verdicts into it; issues no longer open are ignored), `artifact-url.txt` (the board's link),
`board.html`, `current.json` (the live copy of the data) and `last-synced.json`. Make the folder if it is missing.

1. Write `verdicts.json` keyed by friendly id, with `verdict` (bug, regression, expected, outside, parked),
   `group`, `cause`, `action`, `owner`, and optionally `options` and `comment`. It may also carry `_work` (the fix
   steps: state, size, deps, the issues each fixes, PR links) and `_meta` (`eyebrow`, `subtitle`, `needs`,
   `questions`, `repos`). The header of `scripts/board.py` lists every field.
2. Run `python3 "${CLAUDE_PLUGIN_ROOT}/skills/bugsink-triage/scripts/board.py"`. It writes `board.html` and
   `current.json`.
3. Publish `board.html` with the Artifact tool, with `capabilities: {"db": {}}` the first time and `url` from
   `artifact-url.txt` afterwards, so the link stays the same. Then write the data as below.

The page paints from a copy embedded in it, then follows the database document `board/current`. So there are
two ways to update it:

- **Data changed** (a new triage, a resolve, a PR merging): run `board.py`, then ArtifactData `get` on
  collection `board`, doc `current` for its `version`, then `set` with `file_path` `<state dir>/current.json`
  and `if_version` (omit it when the document does not exist yet). Every open view updates and the user's unsent
  choices stay. Do not republish for this.
- **Template changed** (`board.template.html`, for example after a plugin update): publish `board.html`, then
  write `current.json` as above.

Each card has radio options (the first is the recommendation). Picking a resolve option shows a comment box
pre-filled with a suggested comment (set `comment` per issue to change the suggestion). The user can edit it,
and the saved choice carries the final text in `comment`: post exactly that when you resolve. The user picks,
presses Submit, and the choices land in the `decisions` collection. Read them with ArtifactData (action `list`,
collection `decisions`) when they say they have submitted; nothing reaches the chat by itself. Act only on the
choices they made, through `act.py`, and name each resolve in your reply. Then mark each document you handled:
ArtifactData `update` on `decisions/<doc id>` with `status: done`, `handledAt` (ISO time) and `results` (a map
of issue id to one plain sentence of what was done), pinned with `if_version`. The card then shows Done with that
sentence. Cards show Submitted, Changed and Done from that collection.

**GitHub awareness (optional, needs the `gh` CLI, signed in).** A `_meta.needs` entry may be
`{"text": "...", "url": "<pull request URL>"}`: each build reads the PR's state with `gh`, so a merged PR lands its
step and drops its line. With `repos` (in `_meta` or the config; `["owner/repo", ...]`) the board also finds open
PRs that mention an open issue's id in their title, body or branch, adds a "Merge ..." line and links the PR on the
card. `board.py --prs-only` re-reads GitHub alone in a few seconds, with no Bugsink call, and prints `changed` or
`no change` against `last-synced.json`. When it prints `changed`, write `current.json` to `board/current` as above
and copy it over `last-synced.json`. `--no-prs` skips GitHub. Without `gh`, everything else works and the board
just does not track PRs.

**PR owners (optional).** `prSessions` (in `_meta` or the config) maps a PR URL to the session that owns it,
`{"id": "...", "name": "..."}`. The board shows that name as text beside the PR's Merge line, since that is
where its Merge button is. If your Claude Code app can list the PRs bound to a session, use that to fill the map;
otherwise the user can write it by hand. Whoever merges a PR that touches an open issue refreshes the board straight
after (`board.py --prs-only`, then the `board/current` write), so a merge shows in seconds.

**Scheduling (optional).** The plugin ships no scheduled tasks. The README has a recipe for a daily triage and a
frequent `--prs-only` refresh that the user can create themselves.

The page is a snapshot of Bugsink and GitHub, so rebuild it after any resolve. It holds issue ids, device models
and error text and never a token. Check the error text for anything private before publishing.

## Hand-offs: make sure delegated work reports back

When you give work to another session (a fix, a build, an update), do not rely on that session remembering to
answer. This needs only Claude Code and the board's database. Without the Artifact tool, keep a list of what you
delegated in your report and chase it yourself. Each hand-off has two parts.

1. **A record on the board.** Run `handoff.py new --to-id <id> --to-name <name> --task "<what was asked>"
   --step <_work code> --issues <friendly ids>`. It prints the document and a doc id. Write the document to the
   `handoffs` collection with ArtifactData `set`. Its fields are `{to: {id, name}, task, step, issues, askedAt,
   dueAt, status: "open"}`, and `dueAt` defaults to `handoffDueHours` (24) from now. The board lists it under
   "Waiting on sessions" and on each issue's card, amber once overdue.
2. **A close-out line in the brief.** End every hand-off message with the `close_out` line `handoff.py` prints. It
   asks the session to send the evidence (a PR link, release or update ids) back to you, then to mark the record
   done: ArtifactData `update` on `handoffs/<doc id>` with `status: "done"`, `doneAt` (ISO time) and `evidence`
   (one plain sentence), pinned with `if_version`, giving it the artifact URL from `artifact-url.txt`.

A delegated step is not landed until there is evidence: a merged PR (the refresh checks GitHub) or the ids the
session reports. When you read a report, update the `_work` step, the issue's `action` text and the hand-off, then
refresh the board. Report any overdue hand-off in your summary, chase it with a message to the session, and if the
session is gone, say so and ask the user.

