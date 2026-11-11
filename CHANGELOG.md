# Changelog

## 0.1.0

First release.

- Skill `bugsink-triage`: check, trace, classify, report, act.
- `check.py` lists open issues with the latest event, tags, device and the top of the trace.
- `act.py` comments, resolves, reopens and mutes. It never deletes, and it only acts with `--yes`.
- `board.py` builds an optional one-page triage board for claude.ai Artifacts.
- Commands `/bugsink-triage:check` and `/bugsink-triage:board`.
- Tests against a mocked Bugsink using synthetic fixtures.
