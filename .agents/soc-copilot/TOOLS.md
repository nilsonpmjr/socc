# TOOLS

## Available tool categories

### Local LLM adapter

- Purpose: send prompts to the local model and receive structured answers
- Expected implementation: `semi_llm_adapter`
- Notes: prefer JSON-oriented prompting and bounded context windows

### Draft and prompt engine

- Purpose: compose the final prompt from persona, skill, memory, and runtime context
- Expected implementation: `draft_engine`
- Notes: keep prompt assembly deterministic and inspectable

### Threat intelligence and enrichment

- Purpose: enrich payload analysis with known context, lookups, and reference data
- Expected implementation: `ti_adapter`
- Notes: enrichment should be traceable in the final answer

### Future integrations

- RAG retriever for internal intelligence sources
- n8n for operational automation
- MITRE mapping support

## Guardrails

- A declared tool must correspond to a real backend capability.
- Tool availability should be feature-flagged when needed.
- Missing tools must degrade gracefully.
