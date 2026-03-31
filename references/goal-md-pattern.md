# GOAL.md Pattern

Computable fitness function for the project. Defines success criteria and trust tiers.

## Structure

```markdown
# Project Goal

## Mission
[1 sentence: what this project does and why it matters]

## Current Priorities
- [Priority 1: most important thing right now]
- [Priority 2]
- [Priority 3 (optional)]

## Trust Tiers

| Tier | Actions | Human review |
|------|---------|-------------|
| `auto` | lint, format, unit tests | Never |
| `pr` | dependency updates, schema changes | Before merge |
| `alert` | production deploys, data migrations | Explicit approval |

## Fitness Function

| Metric | Target | Source |
|--------|--------|--------|
| [metric name] | [threshold] | [detection basis] |
```

## 2 Questions to Ask (interactive mode)

1. "What's the one-sentence mission of this project?" → fills `Mission`
2. "What are the 2-3 current priorities?" → fills `Current Priorities`

In headless mode: use `[PLACEHOLDER]` for both.

## Metric Inference from detect.sh

Apply these rules based on detection output:

| Detection | Metric to add | Target |
|-----------|--------------|--------|
| `frameworks` includes `vitest` or `jest` | `test_coverage` | `≥ 80%` |
| `frameworks` includes `playwright` | `e2e_pass_rate` | `100%` |
| `infra` includes `github-actions` | `build_time` | `≤ 2min` |
| `.eslintrc` or eslint in deps | `lint_errors` | `0` |
| `go.mod` exists | `test_coverage` | `≥ 70%` |
| `pytest.ini` or pyproject pytest | `test_coverage` | `≥ 80%` |

**Always include at minimum:**
- `lint_errors: 0` (if any linter detected)
- `build_passing: true` (always)

## Trust Tiers (always include these 3)

```markdown
## Trust Tiers

| Tier | Actions | Human review |
|------|---------|-------------|
| `auto` | lint, format, unit tests, docs | Never |
| `pr` | dependency updates, schema changes, new features | Before merge |
| `alert` | production deploys, data migrations, auth changes | Explicit approval |
```

## Smart Merge

- If `GOAL.md` exists and user is interactive → show diff, ask "update / keep"
- If headless → NEVER overwrite existing GOAL.md
- If missing → generate from scratch using detect output + answers to 2 questions
