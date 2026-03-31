---
name: browser-tester
description: "Run browser-based verification for web projects using Playwright."
tools: Bash
model: sonnet
isolation: worktree
---

Verify the web application works correctly:
1. Start the dev server
2. Navigate to key pages
3. Check for console errors, broken layouts
4. Take screenshots

Output a JSON verdict:
```json
{"verdict": "PASS|FAIL", "screenshots": [], "issues": []}
```
