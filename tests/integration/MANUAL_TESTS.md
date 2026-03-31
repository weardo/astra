# Manual E2E Tests (require live Claude Code session)

## Test 1: /astra-init on counter-app
1. `cd tests/fixtures/counter-app`
2. `/astra-init .`
3. Verify: CLAUDE.md, AGENTS.md, GOAL.md, astra.yaml, .mcp.json created

## Test 2: /astra-run with --plan
1. `/astra-run --plan tests/fixtures/sample_work_plan.json`
2. Verify: planner skipped, generator dispatched, sentinel file created

## Test 3: /astra-status
1. `/astra-status`
2. Verify: shows run progress, tasks, current phase

## Test 4: /astra-resume after context exhaustion
1. Start `/astra-run "Add hello endpoint"`, let it checkpoint
2. `/astra-resume`
3. Verify: picks up at correct task

## Test 5: CLI orchestrator standalone
```bash
PYTHONPATH=. python3 -m src.core init \
  --data-dir /tmp/test-astra \
  --prompt "Add a hello endpoint" \
  --detection '{"stack": "typescript", "test_command": "npm test"}'
```
Verify: JSON action output with `dispatch_agent` + `architect` role.
