# Skills Catalog

Curated artifact library with stack triggers and install guidance.

## Superpowers Plugin Bundle

Install from: `.superpowers/` plugin or manual copy.

**Always recommended (any project):**

| Skill | Purpose | Activation |
|-------|---------|-----------|
| `brainstorming` | Creative work gating — explores intent before implementation | Auto on feature requests |
| `test-driven-development` | TDD enforcement — tests before code | Auto on feature/bugfix |
| `systematic-debugging` | Structured debugging before guessing | Auto on test failures |
| `verification-before-completion` | Evidence before success claims | Auto before commit/PR |
| `writing-plans` | Plan before multi-step implementation | Auto on multi-file tasks |
| `executing-plans` | TDD execution from plan files | Manual via `/implement` |

**Recommended for brownfield projects:**

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `brownfield-guard` | `size == "brownfield"` | Pattern discovery before writing new code |
| `requesting-code-review` | any | Code review before merging |
| `receiving-code-review` | any | Technical rigor when handling feedback |

**Optional (by need):**

| Skill | When to add |
|-------|------------|
| `dispatching-parallel-agents` | Complex multi-task work |
| `using-git-worktrees` | Feature isolation needed |
| `writing-skills` | Building custom skills |

## Library Artifacts

Organized by domain. Stack triggers determine pre-check default.

### ai-development

| Artifact | Stack Trigger | Purpose |
|----------|--------------|---------|
| `brownfield-guard` | `size == "brownfield"` | Grep for patterns before writing |
| `note-taker` | vault project | Correct note creation for Obsidian vaults |
| `knowledge-linker` | vault project | Wiki-link injection after note creation |
| `explore-and-document` | any | Research + capture pattern before repeating |
| `bootstrap-project` | any | This skill — apply to nested projects |
| `context-window-mgmt` | any long-running | Compact at 30%, never exceed 90%, session boundaries = commits |
| `long-running-harness` | multi-session tasks | Initializer+Coding or Planner+Generator+Evaluator scaffold; JSON feature contracts; session startup protocol |

### coding

| Artifact | Stack Trigger | Purpose |
|----------|--------------|---------|
| `write-unit-test` | any with test framework | TDD unit test scaffolding |
| `write-e2e-test` | `frameworks` includes web | E2E test scaffolding |
| `api-contract-review` | API project detected | Enforce API design standards |

### workflow (AIDD Pipeline)

| Artifact | Purpose |
|----------|---------|
| `prime` | Session startup orientation |
| `specify` | Spec co-authoring with research |
| `plan` | Implementation plan from spec |
| `implement` | TDD execution from plan |
| `validate` | Spec compliance verification |
| `commit-feature` | Structured commit creation |
| `evolve` | Update reference files after changes |

## Cross-Tool Portability

Skills marked `portable: true` should get a symlink:
```bash
ln -s ../../.claude/skills/<name> .agents/skills/<name>
```

Portable: `brownfield-guard`, `note-taker`, `api-contract-review`, `explore-and-document`
NOT portable (CC-specific `!command` or tool refs): `bootstrap-project`, `retro`

## Stale Detection

Compare installed `SKILL.md` SHA256 vs library version:
```bash
sha256sum .claude/skills/<name>/SKILL.md
sha256sum vault/library/<domain>/<name>/SKILL.md
```
If different → offer update.

## Scoring Logic

Apply stack triggers from detect.sh output:
1. `size == "brownfield"` → pre-check `brownfield-guard`, `write-unit-test`
2. `frameworks` includes web framework → pre-check `write-e2e-test`
3. API routes detected (Express/FastAPI) → pre-check `api-contract-review`
4. Insights `prioritizedHooks` → adjust hook recommendations
5. All superpowers "always recommended" → pre-checked by default
6. Insights `context_exhaustion > 2` → pre-check `context-window-mgmt`
7. Insights `context_exhaustion > 2` OR `fileCount > 500` OR `size == "brownfield"` with large scope → offer `long-running-harness` as opt-in `[ ]`
