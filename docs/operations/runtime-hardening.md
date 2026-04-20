# Runtime Hardening

Use this page when you want to validate the local runtime before trusting it for real analyst work.

## Recommended Checks

```bash
bun run smoke
bun run doctor:runtime
bun run doctor:runtime:json
bun run doctor:report
bun run verify:privacy
bun run hardening:check
bun run hardening:strict
```

## What These Checks Cover

| Command | Purpose |
| --- | --- |
| `bun run smoke` | Confirms the built CLI starts and reports its version |
| `bun run doctor:runtime` | Verifies provider settings and connectivity assumptions |
| `bun run doctor:runtime:json` | Emits machine-readable diagnostics |
| `bun run doctor:report` | Writes a persisted report to `reports/doctor-runtime.json` |
| `bun run verify:privacy` | Checks the no-phone-home privacy expectations |
| `bun run hardening:check` | Runs smoke plus runtime doctor |
| `bun run hardening:strict` | Adds a project-wide typecheck on top of the hardening flow |

## Operational Guidance

- Fail closed on placeholder keys and missing provider credentials
- Prefer explicit provider validation before long-running sessions
- Treat local backends differently from hosted APIs; some do not require API keys
- Re-run diagnostics after changing provider, base URL, or model routing settings

## Analyst Safety

- SOCC is support tooling, not an authority
- Validate model output against original evidence before taking action
- Keep especially sensitive investigations inside trusted local or enterprise-controlled provider paths when possible

## Related Docs

- [Provider Setup](../configuration/providers.md)
- [Advanced Setup](../install/advanced-setup.md)
- [Security Policy](../../SECURITY.md)
