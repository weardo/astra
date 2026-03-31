---
name: astra-status
description: "Use when checking the status of an astra run. Shows tasks done/total, costs, duration, current phase. Do NOT use to start or resume runs."
user-invokable: true
argument-hint: "[run-id]"
---

# /astra-status — Run Status

1. If `$ARGUMENTS` provided: resolve that run. Otherwise: show current run.
2. If no argument and no current run: list all runs via `RunManager.list_runs()`.

3. For a specific run, replay events.jsonl and display:

```
## Run: 001-feature-20260331-1200
Phase: generator (task 3/8)
Tasks: 2 done, 1 in progress, 5 pending
Duration: 12m
Events: 15

### Task History
| Task | Status | Attempts |
|------|--------|----------|
| t1   | done   | 1        |
| t2   | done   | 2        |
| t3   | active | 1        |
```
