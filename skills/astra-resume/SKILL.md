---
name: astra-resume
description: "Use when resuming an interrupted astra run. Reconstructs state from events.jsonl and re-enters the executor loop. Do NOT use for new runs — use /astra-run instead."
user-invokable: true
argument-hint: "[run-id]"
---

# /astra-resume — Resume Interrupted Run

1. Get the next action from the orchestrator:
```bash
PYTHONPATH=${CLAUDE_PLUGIN_ROOT} python3 -m src.core resume \
  --data-dir .astra \
  --run-dir "${RUN_DIR}"
```

2. Enter the same executor loop as /astra-run (dispatch_agent / hitl_gate / complete / error).
