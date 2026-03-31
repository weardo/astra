---
name: astra-run
description: "Use when starting a feature or bugfix implementation run. Orchestrates planning (architect → adversary → refiner → validator), then generator/evaluator loop with circuit breaker, scope drift detection, and HITL gates. Do NOT use for project setup — use /astra-init instead."
user-invokable: true
argument-hint: "[prompt | --spec path | --plan path]"
---

# /astra-run — Feature/Bugfix Implementation

Orchestrate a full implementation run: planning → generation → evaluation → (optional) PR.

## Input

- `$ARGUMENTS` — one of:
  - A natural language prompt (e.g., "Add user authentication")
  - `--spec path/to/spec.md` — skip to planning from an existing spec
  - `--plan path/to/work_plan.json` — skip planning, start generation

## Section 1: Input Resolution

1. Parse `$ARGUMENTS` to determine input mode: `prompt`, `spec`, or `plan`
2. Load `astra.yaml` (or auto-generate from detection if missing)
3. Create run directory via `RunManager.create_run(strategy)`
4. Write sentinel file `.astra-active-run` pointing to run directory
5. Append `run_started` event to `events.jsonl`

```python
from src.core.runs import RunManager
from src.core.event_store import EventStore
from src.core.config import load_config
```

## Section 2: Planner Pipeline

### Step 1: Load Context
- Read `detection.json` (from `/astra-init` or re-detect)
- Generate lightweight repo map
- Read `insights.json` if available

### Step 2: Input Mode Branching
- **prompt mode**: Full pipeline (architect → adversary → refiner → validator)
- **spec mode**: Architect reads spec as input, then adversary → refiner → validator
- **plan mode**: Skip entire planner pipeline, load work_plan.json directly

### Step 3: Dispatch Planner Roles

For each role in the pipeline, dispatch as an Agent call:

```
Agent(
    prompt=build_role_prompt(role, prompts_dir, replacements),
    model=resolve_model(role, config),
)
```

### Step 4: Adaptive Depth

Count tasks in the work plan to determine pipeline depth:
- **Light** (≤5 tasks): architect → validator (skip adversary/refiner)
- **Standard** (6-19 tasks): architect → adversary → refiner → validator
- **Full** (≥20 tasks): architect → adversary → refiner → adversary → refiner → validator

### Step 5: Auto-Fix Dependencies

After each planner role writes the work plan, the `auto_fix_deps.sh` hook fires automatically to chain tasks sharing `target_files`.

### Step 6: HITL Gate — post_plan

Present the work plan summary to the user for confirmation.
- **continue**: proceed to generator loop
- **modify**: apply user instructions, re-run refiner
- **abort**: clean up and exit

```python
from src.core.hitl import hitl_gate
```

## Section 3: Generator/Evaluator Loop

[PLACEHOLDER — completed in Session 4.1]

## Section 4: PR Lifecycle

[PLACEHOLDER — completed in Session 7.1]

## Completion

1. Delete sentinel file `.astra-active-run`
2. Append `run_completed` event
3. Output final summary: tasks done, costs, duration

## Rules

- ALWAYS write sentinel file before dispatching any agent
- ALWAYS write current_task.json before each generator dispatch
- ALWAYS delete sentinel on completion or error
- Circuit breaker checks after every task
- HITL gates at: post_plan, on_circuit_break, budget_warning, pre_merge
