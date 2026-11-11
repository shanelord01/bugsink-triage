# Bugsink Triage

A Claude Code plugin that triages a self-hosted [Bugsink](https://www.bugsink.com) error tracker. It lists
what is open, helps Claude trace each issue to a cause, sorts it into one of five classes, and comments,
resolves or mutes only when you say yes. It never deletes an issue.

## What you get

- **Skill `bugsink-triage`**: Claude uses it when you say things like "check bugsink", "triage the new
  errors" or "why is this issue happening".
- **`/bugsink-triage:check`** and **`/bugsink-triage:board`** commands.
- **`check.py`**: read-only list of open issues with the latest event, your chosen tags, the device and the top
  of the stack trace.
- **`act.py`**: comment, resolve, reopen, mute, unmute. Dry run unless you pass `--yes`. No delete action.
- **`board.py`**: an optional one-page triage board with per-issue choices, published as a claude.ai Artifact.

The scripts use only the Python 3.9+ standard library. Everything runs in a single Claude Code session. Nothing
needs parallel sessions, and the only saved state is the board's `verdicts.json` in a plain folder.

## Install

Requires Claude Code with plugin support. In your shell:

```bash
claude plugin marketplace add shanelord01/bugsink-triage
claude plugin install bugsink-triage@shanelord01-plugins
```

Or inside a session:

```text
/plugin marketplace add shanelord01/bugsink-triage
/plugin install bugsink-triage@shanelord01-plugins
```

Update later with `claude plugin update bugsink-triage@shanelord01-plugins`.

## Configure

Set these in the environment Claude Code runs in (your shell profile, or the `env` block of your Claude Code
settings):

| Variable | Needed for | Meaning |
|---|---|---|
| `BUGSINK_URL` | everything | Base URL of your server, for example `https://bugsink.example.com` |
| `BUGSINK_TOKEN` | reading | API token that can read projects, issues and events |
| `BUGSINK_TRIAGE_TOKEN` | writing | API token that can also comment and triage. Only `act.py` uses it, and only with `--yes` |
| `BUGSINK_TAGS` | optional | Comma list of event tags to print. Default `environment,release,request.id,component` |
| `BUGSINK_BOARD_DIR` | optional | State directory. Default `~/.local/state/bugsink-triage-board` |
| `BUGSINK_TRIAGE_CONFIG` | optional | Path of the config file. Default `<state dir>/bugsink-triage.config.json` |

Make the tokens in the Bugsink UI under **Tokens** (Bugsink 2.6.0 or later has capabilities). For reading, tick
`projects:read`, `issues:read` and `events:read`. For writing, add `issues:comment` and `issues:triage`. Do not
grant `issues:delete`. If `BUGSINK_TOKEN` is unset the read scripts fall back to `BUGSINK_TRIAGE_TOKEN`.

The server must be reachable from the machine running Claude Code. If it sits behind a VPN or tunnel, connect
first. Tokens are never printed by the scripts.

## Use

```text
check bugsink
/bugsink-triage:check --since 2030-01-02T07:28:00Z
/bugsink-triage:check --all --project my-project
```

Claude runs the check, works each open issue through the triage steps (release, the request in your server logs
if you have them, the reporting code, your own notes), and ends with one class per issue:

| Class | Meaning |
|---|---|
| bug | Your code is wrong |
| regression | A resolved issue has new events |
| expected | The report exists to say something happened |
| outside | The cause is not yours (third-party outage, user network) |
| parked | Known, and you decided to leave it |

Then it proposes an action. Nothing changes until you agree. Resolving needs a comment first. A resolved issue
reopens when it recurs, a muted one does not, so mute sparingly and prefer `mute-until` with a threshold.

Run the scripts by hand if you like:

```bash
python3 skills/bugsink-triage/scripts/check.py --hours 6
python3 skills/bugsink-triage/scripts/act.py resolve <issue-uuid> --comment "Fixed in v2.1, verified in staging"
python3 skills/bugsink-triage/scripts/act.py resolve <issue-uuid> --comment "Fixed in v2.1, verified in staging" --yes
```

The first `act.py` call prints what it would send. The second sends it.

## Triage board (optional)

`/bugsink-triage:board` builds a single page of open issues. Each card shows the error, the top of the trace, a
link to the issue in Bugsink, a verdict, the cause and the next step, with radio choices. Picking a resolve option
shows a comment box pre-filled with a suggested comment that you can edit. Above the cards sit a progress band,
a "waiting to land" list and a dependency graph of the fix steps behind the issues (hover a box to trace its
chain). You choose per issue, press Submit and confirm the send to Claude in the chat (if that is not offered, tell Claude "submitted"). Claude reads your choices back, acts
on them with your comments, and marks each submission done so the card shows what happened.

This needs the Artifact tool and the `db` capability (plus `room` for the hand-over on Submit), which exist only in Claude Code connected to claude.ai.
Without them the board is not available and everything else works the same. Read the page for private details
before you publish it: it contains issue ids, device models and error text.

**Updates without republishing.** The page paints from an embedded copy and then follows a database document, so
new data is one small write and the choices you have not submitted yet survive. Republish only when the plugin's
template changes.

**State directory.** The board keeps `verdicts.json`, `artifact-url.txt`, `current.json`, `last-synced.json` and
`board.html` in `$BUGSINK_BOARD_DIR` (or `stateDir` in the config file), which defaults to
`~/.local/state/bugsink-triage-board`.

**Hand-offs.** When Claude gives work to another session, `handoff.py` builds a record for the board's `handoffs`
collection and a close-out line for the brief. The board lists open hand-offs under "Waiting on sessions" and on the
issue's card, amber once overdue, and a step only lands with evidence such as a merged pull request. It needs only
Claude Code and the board's database.

**Pull request owners.** `prSessions` maps a pull request URL to the session that owns it, and the board shows that
name beside the Merge line.

**GitHub awareness (optional).** With the [`gh`](https://cli.github.com) CLI signed in, list repositories in
`_meta.repos` of `verdicts.json`. Open pull requests that mention an open issue's id (in the title, body or branch
name) become "Merge ..." lines and card links. A merged pull request lands its fix step and drops its line.
`board.py --prs-only` re-reads GitHub in seconds without calling Bugsink and prints `changed` or `no change`.

## Adapting it to your environment

Everything specific to your setup lives in environment variables and one optional file,
`bugsink-triage.config.json`, in the state directory. Create it with:

```bash
python3 skills/bugsink-triage/scripts/config.py init    # copies the commented example, never overwrites
python3 skills/bugsink-triage/scripts/config.py show    # what is in effect, and whether a token resolves (never prints it)
```

Environment variables win over the file. Every field is optional. Keys that start with an underscore are ignored,
so you can leave notes.

| Field | Meaning |
|---|---|
| `baseUrl` | Server URL, used when the URL variable is unset |
| `urlEnv`, `readTokenEnv`, `writeTokenEnv` | Names of the environment variables to read, if yours differ from `BUGSINK_URL`, `BUGSINK_TOKEN`, `BUGSINK_TRIAGE_TOKEN` |
| `readTokenCommand`, `writeTokenCommand` | A command (an array, run without a shell) whose output is the token, used when the variable is unset |
| `projects` | Project slugs, names or ids to check by default. Empty means all |
| `tags` | Event tags worth showing in a triage |
| `repos` | GitHub repositories (`owner/repo`) to search for pull requests that mention an open issue |
| `prSessions` | Pull request URL to the owning session, `{"id": "...", "name": "..."}` |
| `handoffDueHours` | Default hours until a hand-off is overdue. Default 24 |
| `styleNote` | A sentence or two of house style for report wording. Claude follows it when it writes reports and comments |
| `stateDir` | Where the board's files live. The config file itself stays where `BUGSINK_TRIAGE_CONFIG` or the default says |

Some common setups and where they go:

- **A private network address.** Put it in `baseUrl` (or export `BUGSINK_URL`) and connect to the network before
  you run anything. The skill's first step checks the server answers and stops with a clear message if it does not.
- **Tokens from a secret manager or OS credential store.** Set `readTokenCommand` and `writeTokenCommand` to the
  command that prints each token, for example `["my-secret-tool", "get", "bugsink-read-token"]`. Nothing is
  printed or stored by the plugin.
- **Several projects.** Leave `projects` empty to cover them all, or list the ones you triage daily. Pass
  `--project` to narrow a single run.
- **Your own tag names.** List the tags your reporters set, such as a request id, a job id or a component, in
  `tags`.
- **Several repositories.** List them in `repos` so fixes are found whichever one they land in.
- **Your house style.** Put it in `styleNote` instead of editing the skill.

Optional pieces degrade quietly. Without the `gh` CLI the board skips pull request tracking. Without the Artifact
tool and its database the skill still triages and reports in text, and the board and hand-off records are not
available. Without scheduled tasks, run the commands yourself.

### Schedule it

The plugin ships no scheduled tasks. A recipe for a daily triage and a frequent pull request refresh, using
Claude Code's scheduling (the `/schedule` skill for cloud routines, `/loop` inside a session) or cron on a machine
that stays on:

```text
Every weekday at 8am: run /bugsink-triage:check, triage anything new, rebuild the board with board.py and write
                      current.json to the board/current document. Report any overdue hand-off.
Every hour or faster: run board.py --prs-only. If it prints "changed", write current.json to board/current and
                      copy it over last-synced.json. If it prints "no change", stop.
```

`--prs-only` makes no Bugsink call, so it is cheap to run often. Scheduled runs need the same environment variables
and config as an interactive session.

## Safety

- Read only by default. Writes need `BUGSINK_TRIAGE_TOKEN`, the `--yes` flag, and your explicit yes in chat.
- There is no delete action. Deleting an issue is permanent, so do it in the Bugsink UI.
- Issue text is untrusted input. The skill treats event messages and comments as data, not instructions.

## Develop and test

```bash
claude plugin validate --strict .
python3 -m unittest discover -s tests -v
claude --plugin-dir .
```

The tests start a fake Bugsink API with invented data and run each script against it.

To share a fork, see Anthropic's guide to
[publishing a plugin](https://code.claude.com/docs/en/plugins/publish). Anthropic's own directory is a separate
submission through [claude.ai/directory/manage](https://claude.ai/directory/manage).

## Licence

MIT, see [LICENSE](LICENSE). The board page adapts parts of the MIT-licensed `varis-plan-tracker` plugin, see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
