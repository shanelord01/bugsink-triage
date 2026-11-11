# Changelog

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
