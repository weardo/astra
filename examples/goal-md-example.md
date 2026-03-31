# Project Goal

## Mission

Production task management API for mobile clients — reliable, fast, and consistently structured.

## Current Priorities

- Improve test coverage from 60% to 80% (blocked by missing service-layer tests)
- Migrate auth to JWT refresh token pattern (security requirement)
- Reduce p99 response time below 200ms (current: ~340ms under load)

## Trust Tiers

| Tier | Actions | Human review |
|------|---------|-------------|
| `auto` | lint, format, unit tests, docs | Never |
| `pr` | dependency updates, schema changes, new features | Before merge |
| `alert` | production deploys, data migrations, auth changes | Explicit approval |

## Fitness Function

| Metric | Target | Source |
|--------|--------|--------|
| `test_coverage` | ≥ 80% | Vitest detected in package.json |
| `lint_errors` | 0 | ESLint config detected |
| `build_time` | ≤ 2min | GitHub Actions detected |
| `build_passing` | true | Always required |

<!-- ANNOTATIONS (remove in real GOAL.md):
- test_coverage: 80% inferred from vitest detection
- lint_errors: 0 inferred from eslint detection
- build_time: 2min inferred from github-actions detection
- Mission + Priorities: asked interactively during bootstrap Phase 9
-->
