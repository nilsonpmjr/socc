# SOCC

Security operations copiloto for threat intelligence, suspicious artifact triage, investigation support, and incident response.

[![PR Checks](https://github.com/nilsonpmjr/socc/actions/workflows/pr-checks.yml/badge.svg)](https://github.com/nilsonpmjr/socc/actions/workflows/pr-checks.yml)
[![Documentation Status](https://readthedocs.org/projects/socc/badge/?version=latest)](https://socc.readthedocs.io/en/latest/)
[![Node.js](https://img.shields.io/badge/Node.js-20%2B-339933)](https://nodejs.org/)
[![Bun](https://img.shields.io/badge/Bun-1.3.11-f6dece)](https://bun.sh/)
[![Security Policy](https://img.shields.io/badge/security-policy-0f766e)](SECURITY.md)
[![License](https://img.shields.io/badge/license-MIT-2563eb)](LICENSE)

[Documentation](https://socc.readthedocs.io/en/latest/) | [Quick Start](https://socc.readthedocs.io/en/latest/install/quickstart.html) | [Advanced Setup](https://socc.readthedocs.io/en/latest/install/advanced-setup.html) | [Security](SECURITY.md) | [Contributing](CONTRIBUTING.md)

---

SOCC keeps the terminal-first, agentic runtime from the current codebase and repackages it for security operations workflows. The core product stays focused on analyst support: one CLI for provider setup, tool-driven investigation, MCP integrations, streaming output, and automation-friendly execution.

## What SOCC Includes

| Area | Description |
| --- | --- |
| Analyst Copilot | Investigate alerts, logs, payloads, URLs, and suspicious artifacts from a terminal-first workflow |
| Multi-provider Runtime | OpenAI-compatible providers, Gemini, GitHub Models, Codex, Ollama, Atomic Chat, and other supported backends |
| Agentic Tooling | Prompts, tools, agents, slash commands, MCP, and streaming output for guided investigation workflows |
| Headless Automation | gRPC server mode for external clients, custom UIs, and pipeline integration |
| Local + Remote Models | Cloud APIs, local inference, and profile-based routing for latency or cost tradeoffs |
| Developer Surfaces | Source build, runtime diagnostics, provider bootstrap scripts, and a VS Code extension package |

## Quick Start

Install the CLI:

```bash
npm install -g @vantagesec/socc
```

Start SOCC:

```bash
socc
```

Inside SOCC:

- run `/provider` for guided provider setup and saved profiles
- run `/onboard-github` for GitHub Models onboarding
- start with a payload, alert, URL, log excerpt, or investigative question

If you want a source build, provider-specific examples, or runtime diagnostics, go straight to the [documentation hub](https://socc.readthedocs.io/en/latest/).

## Documentation

- Installation: [requirements](https://socc.readthedocs.io/en/latest/install/requirements.html), [quick start](https://socc.readthedocs.io/en/latest/install/quickstart.html), [Windows setup](https://socc.readthedocs.io/en/latest/install/windows.html), [advanced setup](https://socc.readthedocs.io/en/latest/install/advanced-setup.html)
- Configuration: [provider setup](https://socc.readthedocs.io/en/latest/configuration/providers.html), [LiteLLM proxy](https://socc.readthedocs.io/en/latest/configuration/litellm.html)
- Operations: [runtime hardening](https://socc.readthedocs.io/en/latest/operations/runtime-hardening.html), [headless gRPC](https://socc.readthedocs.io/en/latest/operations/headless-grpc.html)
- Architecture: [system overview](https://socc.readthedocs.io/en/latest/architecture/overview.html), [runtime map](https://socc.readthedocs.io/en/latest/architecture/runtime.html)
- Contribution: [contributor guide](https://socc.readthedocs.io/en/latest/contributing/index.html)

## Security Notes

- Treat SOCC as analyst support, not as an autonomous authority.
- Validate IOCs, findings, and conclusions before escalation, blocking, containment, or external reporting.
- Separate observed evidence from model inference, especially in incident response and threat intelligence workflows.
- Smaller or cheaper models may degrade investigation quality; verify important outputs against source evidence.

For vulnerability reporting and disclosure expectations, see [SECURITY.md](SECURITY.md).

## Development

```bash
bun install
bun run build
node dist/cli.mjs
```

Common validation commands:

- `bun run smoke`
- `bun test`
- `bun run test:coverage`
- `bun run doctor:runtime`
- `bun run verify:privacy`

## Community

- [GitHub Discussions](https://github.com/nilsonpmjr/socc/discussions) for Q&A, ideas, and community conversation
- [GitHub Issues](https://github.com/nilsonpmjr/socc/issues) for confirmed bugs and actionable feature work

## License

SOCC is released under the terms described in [LICENSE](LICENSE).
