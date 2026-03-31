# Agents Catalog — Bootstrap Project 2.1

Curated agent definitions for Phase 10 generation. Three tiers: always, stack-triggered, optional.

**quality-gate:** System prompt ≤ 80 lines, description passes CSO test (imperative trigger phrase, concrete context, no filler).

**Catalog source resolution (§6.3):**
1. This embedded catalog is always used (always present, no env dependency)
2. If `${BRAIN_DIR:-$HOME/brain}/vault/library/ai-development/awesome-claude-code-subagents/` exists: overlay — library entries for same role take precedence

---

## always

Agents generated for every project regardless of stack.

## code-reviewer
- role: code-reviewer
- source: embedded
- triggers: any
- tools: Read, Grep, Glob, Bash
- model: haiku
- description: "Review code changes for quality, security, and correctness after any implementation task"
- quality: verified (≤80 lines, CSO description)
- notes: Reads git diff to focus on changed files only; checks test coverage before reporting

## researcher
- role: researcher
- source: embedded
- triggers: any
- tools: Read, Grep, Glob, WebSearch, WebFetch
- model: haiku
- description: "Research topics, libraries, and approaches when explicitly asked — returns structured findings with citations"
- quality: verified (≤80 lines, CSO description)
- notes: Scoped to research only — no file writes, no implementation

---

## stack-triggered

Agents generated when detection signals match.

## test-runner
- role: test-runner
- source: embedded
- triggers: test-framework (vitest, jest, pytest, go test)
- tools: Bash
- model: haiku
- description: "Run the project test suite and report failures with file and line context when asked to verify work"
- quality: verified (≤80 lines, CSO description)
- notes: Redundancy filter: skip if test-runner.sh hook installed (see spec §6.2)

## typescript-specialist
- role: typescript-specialist
- source: embedded
- triggers: typescript
- tools: Read, Grep, Bash
- model: sonnet
- description: "Fix TypeScript type errors, strict-mode violations, and lint issues when tsc or eslint output is provided"
- quality: verified (≤80 lines, CSO description)
- notes: Runs tsc --noEmit and eslint before reporting; follows existing tsconfig.json settings

## python-specialist
- role: python-specialist
- source: embedded
- triggers: python
- tools: Read, Grep, Bash
- model: sonnet
- description: "Fix Python type annotations, mypy errors, and pytest failures when output is provided"
- quality: verified (≤80 lines, CSO description)
- notes: Follows existing pyproject.toml / setup.cfg configuration; runs mypy and pytest before reporting

## go-specialist
- role: go-specialist
- source: embedded
- triggers: go
- tools: Read, Grep, Bash
- model: sonnet
- description: "Fix Go compile errors, vet warnings, and test failures when go build or go test output is provided"
- quality: verified (≤80 lines, CSO description)
- notes: Runs go vet and go test ./... before reporting; follows idiomatic Go patterns

## browser-tester
- role: browser-tester
- source: embedded
- triggers: playwright
- tools: Bash
- model: sonnet
- description: "Run Playwright end-to-end tests in isolation when browser test suite needs verification"
- quality: verified (≤80 lines, CSO description)
- notes: isolation: worktree (clean state required for browser tests); uses playwright MCP if available

## spec-reviewer
- role: spec-reviewer
- source: embedded
- triggers: goal-md
- tools: Read, Glob
- model: haiku
- description: "Validate implementation output against GOAL.md fitness criteria and spec acceptance criteria before commit"
- quality: verified (≤80 lines, CSO description)
- notes: Read-only — no code changes; compares actual state against GOAL.md thresholds

## ci-checker
- role: ci-checker
- source: embedded
- triggers: github-actions
- tools: Read, Bash
- model: haiku
- description: "Check GitHub Actions workflow syntax and validate CI pipeline configuration when workflow files are changed"
- quality: verified (≤80 lines, CSO description)
- notes: Reads .github/workflows/*.yml; checks YAML syntax and action version pinning

---

## optional

Niche agents shown unchecked on selection screen when detection signal is present. Never auto-selected.

## debugger
- role: debugger
- source: community (VoltAgent/awesome-claude-code-subagents, trimmed)
- triggers: any (always shown, unchecked)
- tools: Read, Grep, Bash, Edit
- model: sonnet
- description: "Systematically debug errors using root-cause analysis when given an error message or failing test"
- quality: community-trimmed (≤80 lines)
- notes: Full VoltAgent version was 200+ lines; trimmed to core workflow. Edit access required for hypothesis testing.

## security-auditor
- role: security-auditor
- source: embedded
- triggers: any (always shown, unchecked)
- tools: Read, Grep
- model: sonnet
- description: "Audit code for OWASP Top 10 vulnerabilities and secrets exposure when security review is requested"
- quality: verified (≤80 lines, CSO description)
- notes: Read-only; no fixes — reports findings with file:line references

## data-scientist
- role: data-scientist
- source: embedded
- triggers: pandas/numpy in requirements.txt or pyproject.toml (shown only if detected)
- tools: Bash, Write
- model: sonnet
- description: "Analyze datasets and write Python analysis scripts using pandas/numpy when data exploration is requested"
- quality: verified (≤80 lines, CSO description)
- notes: Shown only when pandas or numpy detected in Python project dependencies

## db-reader
- role: db-reader
- source: embedded
- triggers: sqlite/postgres in stack or dependencies (shown only if detected)
- tools: Bash
- model: haiku
- description: "Run read-only SQL queries and explain query plans when database inspection is requested"
- quality: verified (≤80 lines, CSO description)
- notes: Hook-validated read-only SQL (no INSERT/UPDATE/DELETE); shown only when DB detected
