---
name: astra-run
description: "Use when starting a feature or bugfix implementation run. Orchestrates planning, then generator/evaluator loop with circuit breaker and HITL gates. Do NOT use for project setup — use /astra-init instead."
user-invokable: true
argument-hint: "[prompt | --spec path | --plan path]"
---

# /astra-run — Executor Loop

All decisions are made by the Python orchestrator. This skill is a thin executor.

## Setup

1. Parse `$ARGUMENTS`:
   - Plain text → `PROMPT=$ARGUMENTS`
   - `--spec path` → `SPEC_PATH=path`
   - `--plan path` → `PLAN_PATH=path`

2. Load detection (or run detect if missing):
```bash
DETECTION=$(cat .claude/detection.json 2>/dev/null || echo '{}')
```

3. Initialize the orchestrator and get the first action:
```bash
PYTHONPATH=${CLAUDE_PLUGIN_ROOT} python3 -m src.core init \
  --data-dir .astra \
  --project-dir . \
  --prompt "${PROMPT}" \
  --detection "${DETECTION}" \
  --plan "${PLAN_PATH}" \
  --spec "${SPEC_PATH}"
```

This outputs a JSON action. Parse it.

## Executor Loop

Repeat until `action` is `complete` or `error`:

### If action is `dispatch_agent`

1. Read `action.prompt_file`, `action.model`, `action.role` from the JSON
2. Map the role to the correct astra agent:
   ```
   Agent(prompt="Read and follow all instructions in {action.prompt_file}", model=action.model, subagent_type="astra:{action.role}")
   ```
   For example: role "architect" → `subagent_type="astra:architect"`, role "generator" → `subagent_type="astra:generator"`, role "test-runner" → `subagent_type="astra:test-runner"`
3. Save agent output to `action.save_output_to`
4. Get next action:
```bash
PYTHONPATH=${CLAUDE_PLUGIN_ROOT} python3 -m src.core record \
  --data-dir .astra \
  --role "${ROLE}" \
  --output "${OUTPUT}" \
  --task-id "${TASK_ID}" \
  --verdict "${VERDICT}"
```

### If action is `hitl_gate`

1. Present `action.context` to the user
2. Ask: **continue** / **abort** / **modify**?
3. Get next action:
```bash
PYTHONPATH=${CLAUDE_PLUGIN_ROOT} python3 -m src.core record-hitl \
  --data-dir .astra \
  --gate "${GATE}" \
  --decision "${DECISION}" \
  --instructions "${INSTRUCTIONS}"
```

### If action is `checkpoint`

Output `action.summary`. Exit cleanly. User runs `/astra-resume` to continue.

### If action is `complete`

Output `action.summary`. Done.

### If action is `error`

Output `action.message`. Stop.

## Rules

- NEVER make flow decisions — the orchestrator decides
- ALWAYS use `astra:` prefixed agent types — `astra:architect`, `astra:generator`, `astra:test-runner`, etc. NEVER use agents from other plugins (feature-dev, pr-review-toolkit, superpowers).
- ALWAYS save agent output to the path specified by the orchestrator
- ALWAYS pass the full agent output to `record()`
- If the orchestrator says `dispatch_agent`, dispatch the agent
- If the orchestrator says `hitl_gate`, ask the user
- If the orchestrator says `complete`, stop
