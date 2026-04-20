# Runtime Map

This page maps the main repository areas so contributors know where to look before changing behavior.

## Repository Structure

| Path | Purpose |
| --- | --- |
| `src/cli` and `bin/` | CLI entrypoints and launch surfaces |
| `src/commands` | User-facing command handlers |
| `src/components` and `src/screens` | Terminal UI presentation |
| `src/services` | Provider, runtime, and subsystem services |
| `src/tools` | Tool implementations available to the runtime |
| `src/skills` and `src/tasks` | Higher-level workflow primitives |
| `src/proto` and `src/grpc` | gRPC protocol and service plumbing |
| `src/utils` | Shared helpers and supporting infrastructure |
| `scripts/` | Build, diagnostics, bootstrap, and verification scripts |
| `vscode-extension/` | VS Code integration package |

## Runtime State

Important local state surfaces include:

- `~/.socc/settings.json` for saved settings and routing
- `.socc/` inside the repository for bundled agents, references, rules, and skills shipped with the package
- `.omx/` for OMX-specific orchestration state in this workspace

## Validation Surfaces

Common commands tied to runtime health:

```bash
bun run build
bun run smoke
bun test
bun run doctor:runtime
bun run verify:privacy
```

## Change Strategy

- touch the smallest responsible surface
- update docs when setup or runtime behavior changes
- validate the exact provider or execution path you changed whenever possible

## Related Docs

- [Architecture Overview](overview.md)
- [Contributor Guide](../contributing/index.md)
