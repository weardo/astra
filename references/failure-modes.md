# Known Failure Modes — Guard Against These

These failure modes have been observed across harness runs. For each one, take the prescribed guard action immediately when the relevant code is written.

### FM-01: FTS Trigger Omission
**Pattern:** SQLite FTS5 virtual table created without AFTER INSERT / AFTER DELETE / BEFORE UPDATE triggers. Search silently returns nothing.
**Guard:** Immediately after creating any FTS5 virtual table, write all three triggers in the same file.

### FM-02: SSE Subscriber Leak
**Pattern:** SSE endpoint adds clients to a Set but never removes them on disconnect.
**Guard:** Every SSE endpoint must include `req.on('close', () => subscribers.delete(res))` before the first event is sent.

### FM-03: SDK/Import Path Drift
**Pattern:** Different files use different import paths for the same module. TypeScript compiles but runtime fails.
**Guard:** Define the canonical import path in one place (package.json exports or tsconfig paths). Use it consistently.

### FM-04: Empty Error Paths
**Pattern:** Happy path implemented, error paths are empty `catch(e) {}` or bare `res.status(500).send()`.
**Guard:** Every async route must handle: validation error (400), not-found (404), unexpected error (500 with message). Log before responding.

### FM-05: Hardcoded Configurable Values
**Pattern:** Feature claims to use env var but the default is hardcoded and the env var is never read.
**Guard:** Write `const X = process.env.X ?? DEFAULT` and verify it in at least one integration test.

### FM-06: Type-Only Correctness
**Pattern:** TypeScript compiles but runtime behavior diverges — wrong HTTP status codes, missing response fields.
**Guard:** After writing any API endpoint, write a test asserting the exact response body shape and status code.

### FM-07: Docker Health Check Theatre
**Pattern:** Dockerfile has HEALTHCHECK but the health endpoint is not implemented or returns wrong status.
**Guard:** Implement the health endpoint before writing the HEALTHCHECK. Must return 200 with `{"status":"ok"}`.

### FM-08: Cross-Component Integration Gap
**Pattern:** Components work in isolation but the end-to-end path is never tested.
**Guard:** For >2 components, write at least one e2e test crossing all component boundaries.

### FM-09: Partial Docker Networking
**Pattern:** docker-compose.yml services missing networking, volume mounts, or env injection.
**Guard:** Every service must declare its network. Volumes must be named, not anonymous.

### FM-10: Test-Implementation Circularity
**Pattern:** Tests written to match implementation, not spec. Tests pass but feature is wrong.
**Guard:** Read acceptance criteria BEFORE writing the test. Assert the criteria, then implement to pass.
