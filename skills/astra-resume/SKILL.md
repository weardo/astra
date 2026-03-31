---
name: astra-resume
description: "Use when resuming an interrupted astra run. Reconstructs state from events.jsonl and re-enters the executor loop at the correct point. Do NOT use for new runs — use /astra-run instead."
user-invokable: true
argument-hint: "[run-id]"
---

# /astra-resume — Resume Interrupted Run

1. Resolve run directory:
   - If `$ARGUMENTS` provided: `RunManager.resolve_run($ARGUMENTS)`
   - Otherwise: `RunManager.get_current()`

2. Call orchestrator.resume(run_dir) to get the next action.

3. Enter the same executor loop as /astra-run.

The orchestrator replays events.jsonl to determine exactly where to resume.
