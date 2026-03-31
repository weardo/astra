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
DETECTION=$(cat ${PROJECT_DIR}/.claude/detection.json 2>/dev/null || bash ${CLAUDE_PLUGIN_ROOT}/src/scripts/detect.sh .)
```

3. Initialize the orchestrator:
```bash
ACTION=$(python3 -c "
import json, sys
sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
from src.core.orchestrator import Orchestrator
from src.core.config import load_config

config = load_config('${PROJECT_DIR}/astra.yaml')
orch = Orchestrator(
    data_dir='${PROJECT_DIR}/.astra',
    config=config,
    prompts_dir='${CLAUDE_PLUGIN_ROOT}/src/prompts',
    references_dir='${CLAUDE_PLUGIN_ROOT}/references',
)
orch.project_dir = '${PROJECT_DIR}'
action = orch.init(
    prompt='${PROMPT}',
    detection=json.loads('${DETECTION}'),
    plan_path='${PLAN_PATH}' if '${PLAN_PATH}' else None,
)
print(json.dumps(action))
")
```

## Executor Loop

Repeat until `action.action` is `complete` or `error`:

### dispatch_agent
```
Read action.prompt, action.model, action.role from the JSON.
Call: Agent(prompt=action.prompt, model=action.model)
Save agent output to action.save_output_to
Then call orchestrator.record(role, output) to get next action.
```

### hitl_gate
```
Present action.context to the user.
Ask: continue / abort / modify?
Call orchestrator.record_hitl(gate, decision) to get next action.
```

### checkpoint
```
Output action.summary.
Exit cleanly. User runs /astra-resume to continue.
```

### complete
```
Output action.summary.
Done.
```

### error
```
Output action.message.
Stop.
```

## Recording Results

After each agent dispatch, record the result:
```bash
ACTION=$(python3 -c "
import json, sys
sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
from src.core.orchestrator import Orchestrator
# ... reconstruct orchestrator from run_dir ...
action = orch.record(role='${ROLE}', output='''${OUTPUT}''', task_id='${TASK_ID}', verdict='${VERDICT}')
print(json.dumps(action))
")
```

## Rules

- NEVER make flow decisions — the orchestrator decides
- ALWAYS save agent output to the path specified by the orchestrator
- ALWAYS pass the full agent output to `record()`
- If the orchestrator says `dispatch_agent`, dispatch the agent
- If the orchestrator says `hitl_gate`, ask the user
- If the orchestrator says `complete`, stop
