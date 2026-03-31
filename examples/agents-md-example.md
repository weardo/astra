# Agent Instructions for task-api – TypeScript REST API

<!-- Section 1: Required first line, no content below here -->

## Summary

<!-- Section 2: 1-3 sentences + read-depth guidance -->
REST API for managing tasks with TypeScript, Express, and SQLite. Provides CRUD endpoints, JWT authentication, and Vitest test suite.
Scan Summary and Must-follow for quick context. Read all sections for full agent setup.

## Must-follow rules

<!-- Section 3: flat dash list, imperative, max 10 rules, ≤120 chars each -->
- Never modify files outside the project directory
- Run npm test before marking any implementation task complete
- Read existing patterns with grep before creating new abstractions
- Use existing error handler middleware — never throw raw errors in route handlers
- Never commit without running npm run lint first
- Keep route handlers thin — business logic belongs in service layer
- Never add dependencies without checking if an existing package covers the use case

## Must-read documents

<!-- Section 4: flat dash list of files to read -->
- CLAUDE.md — project commands, session lifecycle, AI workflow rules
- docs/api-reference.md — endpoint contracts and response schemas
- src/middleware/ — error handling and auth patterns to follow

## Agent guidelines

<!-- Section 5: behavioral preferences beyond must-follows -->
- Prefer functional patterns over class-based design
- Use descriptive variable names — avoid single-letter variables except in loops
- Add JSDoc comments to exported functions
- When uncertain about scope, ask before implementing rather than guessing
- Log decisions with context: prefer short inline comments over long docs

## Context

<!-- Section 6: project background affecting agent behavior -->
This is a production API serving mobile clients. Response format must be consistent (see api-reference.md). The authentication middleware is stable — do not refactor it. The SQLite schema has migrations in db/migrations/ — always add a migration rather than altering tables directly.

## References

<!-- Section 7: external docs and standards -->
- [Express.js Docs](https://expressjs.com/en/api.html) — routing and middleware
- [Vitest Docs](https://vitest.dev/guide/) — test runner
- [SQLite WAL Mode](https://www.sqlite.org/wal.html) — concurrency notes
