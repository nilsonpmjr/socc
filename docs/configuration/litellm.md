# LiteLLM Proxy Setup

SOCC can connect to LiteLLM through LiteLLM's OpenAI-compatible proxy.

## Overview

LiteLLM gives SOCC a single OpenAI-compatible endpoint that can route requests across many upstream providers.

## Prerequisites

- LiteLLM installed with proxy support
- A `litellm_config.yaml` or equivalent configuration
- A running LiteLLM Proxy instance

## 1. Install and Start LiteLLM

```bash
pip install "litellm[proxy]"
```

Example configuration:

```yaml
model_list:
  - model_name: gpt-4o
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY

  - model_name: claude-sonnet-4
    litellm_params:
      model: anthropic/claude-sonnet-4-5-20250929
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: gemini-2.5-flash
    litellm_params:
      model: gemini/gemini-2.5-flash
      api_key: os.environ/GEMINI_API_KEY
```

Run the proxy:

```bash
litellm --config litellm_config.yaml --port 4000
```

## 2. Point SOCC at LiteLLM

```bash
export SOCC_USE_OPENAI=1
export OPENAI_BASE_URL=http://localhost:4000
export OPENAI_API_KEY=<your-proxy-key-or-placeholder>
export OPENAI_MODEL=<your-litellm-model-alias>

socc
```

`OPENAI_MODEL` must match the alias in `litellm_config.yaml`, not the upstream raw provider model string.

## 3. Using `/provider`

1. Launch `socc`
2. Run `/provider`
3. Choose **OpenAI-compatible**
4. Enter the LiteLLM proxy key or placeholder value
5. Use `http://localhost:4000` as the base URL
6. Enter the model alias from your LiteLLM config

## 4. Troubleshooting

| Issue | Likely Cause | Fix |
| --- | --- | --- |
| 404 or model not found | Model alias mismatch | Verify `OPENAI_MODEL` matches `model_name` |
| Connection refused | Proxy is not running | Start LiteLLM with the correct config and port |
| Auth failed | Wrong proxy or master key | Set the correct key in `OPENAI_API_KEY` |
| Chat works but tools fail | Weak model tool support | Switch to a model with stronger tool calling |

## Resources

- [LiteLLM Proxy Docs](https://docs.litellm.ai/docs/proxy/quick_start)
- [LiteLLM Provider List](https://docs.litellm.ai/docs/providers)
- [OpenAI-Compatible Proxy Docs](https://docs.litellm.ai/docs/proxy/openai_compatible_proxy)
