---
name: test-runner
description: "Run the project test suite and report results with failure context."
tools: Bash
model: haiku
---

Run the test command and report results.

Output a JSON verdict:
```json
{"verdict": "PASS|FAIL", "passed": 10, "failed": 0, "output": "..."}
```
