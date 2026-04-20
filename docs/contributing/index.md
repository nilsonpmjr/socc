# Contributing

SOCC is a fast-moving security-first agentic CLI. The best contributions are focused, tested, and easy to review.

## Before You Start

- Search existing [issues](https://github.com/nilsonpmjr/socc/issues) and [discussions](https://github.com/nilsonpmjr/socc/discussions)
- Use issues for confirmed bugs and actionable feature work
- Use discussions for setup help, ideas, and general conversation
- For larger changes, open an issue first so the scope is clear
- For vulnerability reports, follow [SECURITY.md](../../SECURITY.md)

## Local Setup

```bash
bun install
bun run build
bun run smoke
bun run dev
```

If you are working on provider setup or saved profiles:

```bash
bun run profile:init
bun run dev:profile
```

## Development Workflow

- Keep PRs focused on one problem or feature
- Avoid unrelated cleanup in the same diff
- Preserve existing repo patterns unless the change is intentionally refactoring them
- Add or update tests when the change affects behavior
- Update docs when setup, commands, or user-facing behavior changes

## Validation

Common checks:

```bash
bun run build
bun run smoke
```

Focused tests:

```bash
bun test ./path/to/test-file.test.ts
```

Provider/runtime work should usually also run:

```bash
bun run doctor:runtime
```

## Pull Requests

Good PRs usually include:

- what changed
- why it changed
- the user or developer impact
- the exact checks that were run

If you touch UI or terminal presentation, include screenshots when helpful. If you change provider behavior, say which provider path was tested.

## Reference Files

- [Root contributing guide](../../CONTRIBUTING.md)
- [Security policy](../../SECURITY.md)
