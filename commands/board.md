---
description: Build the Bugsink triage board as a claude.ai Artifact
argument-hint: "[--project NAME]"
---

Use the "Triage board" section of the bugsink-triage skill. Triage the open issues if that has not been done in
this session, write `verdicts.json`, build the board with `board.py`, and publish it with the Artifact tool. If the
Artifact tool or the `db` capability is not available here, say so and show the triage as a table instead.

Arguments: $ARGUMENTS
