# SOCC VS Code Extension

A practical VS Code companion for SOCC with a project-aware **Control Center**, predictable terminal launch behavior, and quick access to useful SOCC workflows.

## Features

- **Real Control Center status** in the Activity Bar:
  - whether the configured `socc` command is installed
  - the launch command being used
  - whether the launch shim injects `CLAUDE_CODE_USE_OPENAI=1`
  - the current workspace folder
  - the launch cwd that will be used for terminal sessions
  - whether `.socc-profile.json` exists in the current workspace root
  - a conservative provider summary derived from the workspace profile or known environment flags
- **Project-aware launch behavior**:
  - `Launch SOCC` launches from the active editor's workspace when possible
  - falls back to the first workspace folder when needed
  - avoids launching from an arbitrary default cwd when a project is open
- **Practical sidebar actions**:
  - Launch SOCC
  - Launch in Workspace Root
  - Open Workspace Profile
  - Open Repository
  - Open Setup Guide
  - Open Command Palette
- **Built-in dark theme**: `SOCC Terminal Black`

## Requirements

- VS Code `1.95+`
- `socc` available in your terminal PATH (`npm install -g @vantagesec/socc`)

## Commands

- `SOCC: Open Control Center`
- `SOCC: Launch in Terminal`
- `SOCC: Launch in Workspace Root`
- `SOCC: Open Repository`
- `SOCC: Open Setup Guide`
- `SOCC: Open Workspace Profile`

## Settings

- `socc.launchCommand` (default: `socc`)
- `socc.terminalName` (default: `SOCC`)
- `socc.useOpenAIShim` (default: `false`)
- `openclaude.launchCommand` / `openclaude.terminalName` / `openclaude.useOpenAIShim` remain readable as legacy fallback keys

`socc.useOpenAIShim` only injects `CLAUDE_CODE_USE_OPENAI=1` into terminals launched by the extension. It does not guess or configure a provider by itself.

## Notes on Status Detection

- Provider status prefers the real workspace `.socc-profile.json` file when present, with fallback to the legacy `.openclaude-profile.json`.
- If no saved profile exists, the extension falls back to known environment flags available to the VS Code extension host.
- If the source of truth is unclear, the extension shows `unknown` instead of guessing.

## Development

From this folder:

```bash
npm run test
npm run lint
```

To package (optional):

```bash
npm run package
```
