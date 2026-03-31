# Generator Recovery Protocol

Injected into generator prompts at runtime. These steps run BEFORE implementation.

## Recovery Check (MANDATORY FIRST STEP)

1. Check if `{{RUN_DIR}}/feedback.md` exists.
   - If YES: Read it. This is evaluator feedback on your previous work. Address ALL issues before new work. Delete feedback.md after fixing.
   - If NO: Continue.

2. Check current_task.json for retry state.
   - If `attempts > 0`: this is a retry. Read previous feedback carefully.

## Regression Check (MANDATORY)

Before starting new work:
1. Run `{{TEST_COMMAND}}` to verify existing tests pass
2. If ANY test fails: fix the regression BEFORE starting new work
3. If web project: check browser for console errors, broken layouts

**If regression found:**
1. Fix the regression first
2. Re-verify all tests pass
3. Then proceed with the assigned task

## Browser Verification (web projects only)

After implementation, if the project has a web UI:
- Navigate to the app in browser
- Interact like a real user (click, type, scroll)
- Take screenshots at each step
- Check for: console errors, broken layouts, white-on-white text
- Do NOT only test with curl
