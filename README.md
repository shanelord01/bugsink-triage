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

`/bugsink-triage:board` builds a single page of open issues with a verdict, cause and next step on each card,
a progress band, a "waiting to land" list and a dependency graph of fixes. You pick an option per issue and press
Submit, then tell Claude "submitted" and it reads your choices back and acts on them.

This needs the Artifact tool and the `db` capability, which exist only in Claude Code connected to claude.ai.
Without them the board is not available and everything else works the same. Read the page for private details
before you publish it: it contains issue ids, device models and error text.

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
