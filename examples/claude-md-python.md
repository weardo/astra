# Project Name — Python

Brief description of what this project does.

## Tech Stack

| Component | Technology | Location |
|-----------|-----------|----------|
| API | Python, FastAPI | `app/` |
| Tests | pytest | `tests/` |
| Package | pyproject.toml | root |

## Build & Test

```bash
pip install -e ".[dev]"
pytest
```

## AI Workflow (MANDATORY)

Follow: Explore → Plan → Implement → Commit

### Context Window Management
1. Compact at 30% remaining — run `/compact` proactively
2. Session boundaries = git commits
3. NEVER run past 90% context

### Development Rules
- NEVER write code before reading existing patterns (grep first)
- NEVER use `import *` — always explicit imports
- ALWAYS add type hints to new functions
- ALWAYS run `pytest` after every change

### Bug Fix Policy
Every bug fix must include a test that fails before the fix, passes after.

<!-- INSIGHTS-DRIVEN RULES: bootstrap-project injects personalized rules here -->

@AGENTS.md
