# Project Name — TypeScript/Node

Brief description of what this project does.

## Tech Stack

| Component | Technology | Location |
|-----------|-----------|----------|
| API | TypeScript, Node.js, Express | `src/` |
| Tests | Vitest | `src/__tests__/` |
| Build | tsc | `dist/` |

## Build & Test

```bash
npm install
npm run build
npm test
```

## AI Workflow (MANDATORY)

Follow: Explore → Plan → Implement → Commit

### Context Window Management
1. Compact at 30% remaining — run `/compact` proactively
2. Session boundaries = git commits
3. NEVER run past 90% context

### Development Rules
- NEVER write code before reading existing patterns (grep first)
- NEVER skip planning for tasks touching more than 2 files
- NEVER use console.log — use console.error for all logging
- ALWAYS run `npm test` after every change

### Bug Fix Policy
Every bug fix must include a test that fails before the fix, passes after.

<!-- INSIGHTS-DRIVEN RULES: bootstrap-project injects personalized rules here -->

@AGENTS.md
