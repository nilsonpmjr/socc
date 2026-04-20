# Windows Setup

This guide uses Windows PowerShell.

## 1. Install Node.js

Install Node.js `20+` from [nodejs.org](https://nodejs.org/), then confirm:

```powershell
node --version
npm --version
```

## 2. Install SOCC

```powershell
npm install -g @vantagesec/socc
```

## 3. Start SOCC

```powershell
socc
```

Inside SOCC:

- run `/provider` for guided provider setup
- run `/onboard-github` for GitHub Models onboarding
- start with an alert, URL, log excerpt, payload, or investigation prompt

## 4. PowerShell Provider Examples

### OpenAI

```powershell
$env:SOCC_USE_OPENAI="1"
$env:OPENAI_API_KEY="sk-your-key-here"
$env:OPENAI_MODEL="gpt-4o"

socc
```

### DeepSeek

```powershell
$env:SOCC_USE_OPENAI="1"
$env:OPENAI_API_KEY="sk-your-key-here"
$env:OPENAI_BASE_URL="https://api.deepseek.com/v1"
$env:OPENAI_MODEL="deepseek-chat"

socc
```

### Ollama

```powershell
ollama pull qwen2.5-coder:7b

$env:SOCC_USE_OPENAI="1"
$env:OPENAI_BASE_URL="http://localhost:11434/v1"
$env:OPENAI_MODEL="qwen2.5-coder:7b"

socc
```

## 5. If `socc` Is Not Found

Close PowerShell, open a new one, and run:

```powershell
socc
```

## 6. Troubleshooting Basics

- For hosted providers, verify the API key and base URL
- For Ollama, make sure the service is running and the model was pulled
- For LM Studio, make sure the server is enabled and the model name matches `OPENAI_MODEL`

## Next Steps

- [Advanced Setup](advanced-setup.md)
- [Provider Setup](../configuration/providers.md)
- [Runtime Hardening](../operations/runtime-hardening.md)
