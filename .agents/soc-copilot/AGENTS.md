# AGENTS

## Orchestration rules

- Load the base persona first.
- Add one specialized skill when the input clearly matches a playbook.
- Use the generic payload triage skill when no specialized playbook is a better fit.
- Apply memory only when it helps standardize behavior or reflect approved conventions.
- Do not let memory override direct evidence from the current artifact.

## Escalation rules

- Ask for human validation before any destructive or blocking action.
- Highlight low-confidence areas explicitly.
- If the model cannot support a verdict, return `inconclusivo`.

## Reasoning contract

- Facts first
- Inferences second
- Recommendations last

## Tooling contract

- Use deterministic extraction when available before relying on the LLM.
- Use the LLM to explain, correlate, and summarize.
- Use enrichment adapters to add context, not to replace validation.
