# Advanced Setup

This guide is for source builds, Bun workflows, profile-based launches, diagnostics, and explicit provider control.

## Install Options

### Option A: npm

```bash
npm install -g @vantagesec/socc
```

### Option B: From Source with Bun

Use Bun `1.3.11` or newer for source builds.

```bash
git clone https://github.com/nilsonpmjr/socc.git socc
cd socc

bun install
bun run build
npm link
```

### Option C: Run Directly with Bun

```bash
git clone https://github.com/nilsonpmjr/socc.git socc
cd socc

bun install
bun run dev
```

## Provider Examples

### OpenAI

```bash
export SOCC_USE_OPENAI=1
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-4o
```

### Codex via ChatGPT Auth

`codexplan` maps to the higher-reasoning Codex route and `codexspark` maps to the faster Codex Spark route.

If you already use Codex CLI, SOCC reads `~/.codex/auth.json` automatically. You can also set `CODEX_AUTH_JSON_PATH` or `CODEX_API_KEY`.

```bash
export SOCC_USE_OPENAI=1
export OPENAI_MODEL=codexplan

socc
```

### DeepSeek

```bash
export SOCC_USE_OPENAI=1
export OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://api.deepseek.com/v1
export OPENAI_MODEL=deepseek-chat
```

### OpenRouter

```bash
export SOCC_USE_OPENAI=1
export OPENAI_API_KEY=sk-or-...
export OPENAI_BASE_URL=https://openrouter.ai/api/v1
export OPENAI_MODEL=google/gemini-2.0-flash-001
```

### Ollama

```bash
ollama pull llama3.3:70b

export SOCC_USE_OPENAI=1
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_MODEL=llama3.3:70b
```

### Atomic Chat

```bash
export SOCC_USE_OPENAI=1
export OPENAI_BASE_URL=http://127.0.0.1:1337/v1
export OPENAI_MODEL=your-model-name
```

### LM Studio

```bash
export SOCC_USE_OPENAI=1
export OPENAI_BASE_URL=http://localhost:1234/v1
export OPENAI_MODEL=your-model-name
```

## Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `SOCC_USE_OPENAI` | Yes | Enables the OpenAI-compatible provider path |
| `OPENAI_API_KEY` | Usually | API key for hosted providers; not needed for some local backends |
| `OPENAI_MODEL` | Yes | Model name such as `gpt-4o`, `deepseek-chat`, or `llama3.3:70b` |
| `OPENAI_BASE_URL` | No | API endpoint; defaults to OpenAI if omitted |
| `CODEX_API_KEY` | Codex only | Codex or ChatGPT access-token override |
| `CODEX_AUTH_JSON_PATH` | Codex only | Path to Codex CLI `auth.json` |
| `CODEX_HOME` | Codex only | Alternate Codex home directory |

`ANTHROPIC_MODEL` can still override model naming in some flows, but `OPENAI_MODEL` takes priority on the OpenAI-compatible path.

## Runtime Hardening

```bash
bun run smoke
bun run doctor:runtime
bun run doctor:runtime:json
bun run doctor:report
bun run hardening:check
bun run hardening:strict
```

Notes:

- `doctor:runtime` fails fast on placeholder keys and missing required credentials
- local providers can run without `OPENAI_API_KEY`
- Codex profiles validate either `CODEX_API_KEY` or the Codex CLI auth file

## Provider Launch Profiles

```bash
bun run profile:init
bun run profile:recommend -- --goal coding --benchmark
bun run profile:auto -- --goal latency
bun run profile:codex
bun run dev:profile
bun run dev:codex
bun run dev:openai
bun run dev:ollama
bun run dev:atomic-chat
```

Use:

- `profile:init` for a first-time guided profile bootstrap
- `profile:recommend` to compare installed models by goal
- `profile:auto` to persist the best available recommendation
- `dev:*` commands to launch from a saved or explicit provider path

## Related Docs

- [Provider Setup](../configuration/providers.md)
- [LiteLLM Proxy Setup](../configuration/litellm.md)
- [Runtime Hardening](../operations/runtime-hardening.md)
