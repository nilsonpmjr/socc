# Architecture Overview

SOCC is a security-focused CLI runtime that combines provider abstraction, interactive terminal UX, tool execution, agent workflows, and optional remote surfaces in one codebase.

## High-Level Layers

| Layer | Responsibility |
| --- | --- |
| CLI Entry | Launch the terminal app and route command flows |
| Runtime Core | Manage sessions, prompts, tool loops, streaming, and orchestration |
| Provider Layer | Normalize OpenAI-compatible and non-compatible model backends |
| Tooling Layer | File, shell, MCP, fetch, and other operator-facing capabilities |
| Integration Layer | gRPC server, IDE integration, and extension surfaces |
| Configuration Layer | Profiles, settings, routing, and local state under `~/.socc` |

## Product Shape

SOCC is not a single-purpose IOC lookup tool. It is a general analyst workstation runtime tuned for security operations use cases:

- threat intelligence
- artifact triage
- investigation support
- incident response assistance

## Design Priorities

- terminal-first analyst experience
- provider portability
- tool-driven workflows instead of pure chat
- local and remote runtime flexibility
- explicit security posture around permissions and external integrations

## Codebase Anchors

- `src/` contains the runtime, commands, tools, services, and UI components
- `scripts/` contains build, bootstrap, diagnostics, and verification flows
- `src/proto/` contains the gRPC protocol definitions
- `vscode-extension/` contains the editor integration package

## Related Docs

- [Runtime Map](runtime.md)
- [Headless gRPC Server](../operations/headless-grpc.md)
- [Provider Setup](../configuration/providers.md)
