# Provider Setup

SOCC supports multiple provider paths, but runtime behavior is not identical across them. Start with the provider that best matches your latency, cost, privacy, and tooling requirements.

## Supported Providers

| Provider | Setup Path | Notes |
| --- | --- | --- |
| OpenAI-compatible | `/provider` or environment variables | Works with OpenAI, OpenRouter, DeepSeek, Groq, Mistral, LM Studio, and other compatible `/v1` servers |
| Gemini | `/provider` or environment variables | Supports API key, access token, or local ADC workflows on the current main branch |
| GitHub Models | `/onboard-github` | Interactive onboarding with saved credentials |
| Codex | `/provider` or profile scripts | Uses Codex CLI credentials when available |
| Ollama | `/provider` or environment variables | Local inference with no API key |
| Atomic Chat | advanced setup | Local Apple Silicon backend |
| Bedrock / Vertex / Foundry | environment variables | Additional enterprise provider paths |

## Recommended Setup Flow

1. Launch `socc`
2. Run `/provider`
3. Choose the provider family
4. Save the profile if the workflow offers it
5. Reopen SOCC or continue the session with an investigative prompt

## Provider Notes

- Tool quality depends heavily on the selected model
- Smaller local models can struggle with long multi-step tool flows
- Some providers impose lower output caps than the CLI defaults
- Anthropic-specific capabilities do not automatically exist on other providers

For best results, prefer models with strong tool or function calling support.

## Agent Routing

SOCC can route different agents to different models through `~/.socc/settings.json`.

```json
{
  "agentModels": {
    "deepseek-chat": {
      "base_url": "https://api.deepseek.com/v1",
      "api_key": "sk-your-key"
    },
    "gpt-4o": {
      "base_url": "https://api.openai.com/v1",
      "api_key": "sk-your-key"
    }
  },
  "agentRouting": {
    "Explore": "deepseek-chat",
    "Plan": "gpt-4o",
    "general-purpose": "gpt-4o",
    "frontend-dev": "deepseek-chat",
    "default": "gpt-4o"
  }
}
```

When no routing match is found, the global provider remains the fallback.

`settings.json` stores `api_key` values in plaintext. Keep the file private and out of version control.

## Web Search and Fetch

By default:

- `WebSearch` can use DuckDuckGo on non-Anthropic models
- Anthropic-native backends and Codex responses keep their native search behavior
- `WebFetch` works for plain HTTP/HTML flows but can fail on JS-heavy sites

Set `FIRECRAWL_API_KEY` if you want Firecrawl-backed search and fetch behavior:

```bash
export FIRECRAWL_API_KEY=your-key-here
```

## Related Docs

- [Advanced Setup](../install/advanced-setup.md)
- [LiteLLM Proxy Setup](litellm.md)
- [Runtime Hardening](../operations/runtime-hardening.md)
