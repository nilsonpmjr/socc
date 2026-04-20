# Quick Start

This path is for macOS and Linux users who want the fastest route from install to first session.

## 1. Install Node.js

Install Node.js `20+` from [nodejs.org](https://nodejs.org/), then confirm:

```bash
node --version
npm --version
```

## 2. Install SOCC

```bash
npm install -g @vantagesec/socc
```

## 3. Start SOCC

```bash
socc
```

Inside SOCC:

- run `/provider` for guided provider setup
- run `/onboard-github` if you want GitHub Models onboarding
- start with a payload, alert, URL, log excerpt, or investigative question

## 4. Fastest Provider Examples

### OpenAI

```bash
export SOCC_USE_OPENAI=1
export OPENAI_API_KEY=sk-your-key-here
export OPENAI_MODEL=gpt-4o

socc
```

### Ollama

```bash
ollama pull qwen2.5-coder:7b

export SOCC_USE_OPENAI=1
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_MODEL=qwen2.5-coder:7b

socc
```

### LM Studio

```bash
export SOCC_USE_OPENAI=1
export OPENAI_BASE_URL=http://localhost:1234/v1
export OPENAI_MODEL=your-model-name

socc
```

Some LM Studio setups also need a placeholder `OPENAI_API_KEY`.

## 5. If `socc` Is Not Found

Close the terminal, open a new one, and run:

```bash
socc
```

## 6. Safety Reminder

- Use SOCC as analyst support, not as the final authority.
- Review important findings before containment, blocking, escalation, or reporting.
- Prefer grounding sessions in concrete evidence rather than generic prompts.

## Next Steps

- [Advanced Setup](advanced-setup.md)
- [Provider Setup](../configuration/providers.md)
- [Runtime Hardening](../operations/runtime-hardening.md)
