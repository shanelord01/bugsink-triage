# Changelog

## 0.4.0

- Submit on the board now offers to send Claude a short note (`kind: bugsink-triage-submit`) through the Artifact `room` capability, so the user confirms once in the chat instead of typing "submitted". Publish with `capabilities: {"db": {}, "room": {}}`. Where that is not offered the page keeps the old wording and the Copy button.

## 0.3.0

- Config file `bugsink-triage.config.json` (example shipped) holds everything environment-specific: server URL,
  token variable names or token commands, default projects, tags, GitHub repos, PR owners, hand-off timing, a
  style note and the state directory. Environment variables still win. New `config.py show|init|path`.
- Hand-offs: a `handoffs` collection on the board database, a "Waiting on sessions" panel, per-card lines (amber
  when overdue), `handoff.py` to build the record and the close-out line for a brief, and the rule that a step
  lands only with evidence. Needs only Claude Code and the board database.
- `prSessions` shows the owning session's name beside a pull request's Merge line.
- Skill text is neutral: house rules moved to the optional `styleNote`. Optional pieces (`gh`, the Artifact tool,
  scheduling) degrade quietly.
- README section "Adapting it to your environment" and a scheduling recipe. Tests cover the config, hand-offs and
  `prSessions` with synthetic data.

## 0.2.0

- Triage board rebuilt: progress band, waiting-to-land list, hover-traced dependency graph of fix steps
  (`_work`), "Needs you" and "Questions" lists (`_meta`), and a Bugsink link on every card.
- The page follows the database document `board/current`, so data updates need no republish, and unsent
  choices survive refreshes.
- Choices: radio options per card, an editable comment box pre-filled for resolve options, Submit to the
  `decisions` collection, and Submitted, Changed and Done states read back from it.
- Optional GitHub awareness through the `gh` CLI: `_meta.repos` finds open pull requests that mention an open
  issue, merged pull requests land their step, and `board.py --prs-only` re-reads GitHub without calling Bugsink.
- `BUGSINK_BOARD_DIR` sets the board's state directory.
- README explains how to schedule a daily triage and a fast `--prs-only` refresh.

## 0.1.0

First release.

- Skill `bugsink-triage`: check, trace, classify, report, act.
- `check.py` lists open issues with the latest event, tags, device and the top of the trace.
- `act.py` comments, resolves, reopens and mutes. It never deletes, and it only acts with `--yes`.
- `board.py` builds an optional one-page triage board for claude.ai Artifacts.
- Commands `/bugsink-triage:check` and `/bugsink-triage:board`.
- Tests against a mocked Bugsink using synthetic fixtures.
