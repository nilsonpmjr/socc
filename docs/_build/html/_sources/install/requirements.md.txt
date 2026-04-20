# Requirements

Use this page to confirm the minimum tooling before installing or building SOCC.

## Runtime Requirements

- Node.js `20+`
- `npm` for global installation
- Internet access for hosted model providers, or a reachable local backend such as Ollama / LM Studio / Atomic Chat

## Recommended Local Tools

- `ripgrep` (`rg`) for the best terminal workflow experience
- A modern terminal with UTF-8 support
- Git if you plan to work from source or contribute changes

If installation later reports `ripgrep not found`, install it system-wide and confirm `rg --version` works in the same shell before starting SOCC.

## Source Build Requirements

- Bun `1.3.11` or newer
- Node.js `20+`
- Native dependencies needed by your chosen local provider, if applicable

## Optional Local Backends

- [Ollama](https://ollama.com/download) for local OpenAI-compatible inference
- [LM Studio](https://lmstudio.ai/) for local OpenAI-compatible model serving
- [Atomic Chat](https://atomic.chat/) for Apple Silicon local inference
- LiteLLM Proxy if you want a single OpenAI-compatible gateway for multiple providers

## Next Steps

- New users should continue with [Quick Start](quickstart.md)
- PowerShell users should use [Windows Setup](windows.md)
- Source builds and profile-based launches are covered in [Advanced Setup](advanced-setup.md)
