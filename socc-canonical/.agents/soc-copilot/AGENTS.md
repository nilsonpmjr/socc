# AGENTS

## Orchestration rules

- Load the base persona first.
- Default to a general SOC conversation mode for open-ended analyst questions.
- Add one specialized skill when the input clearly matches a playbook or artifact family.
- Use the generic payload triage skill only when the input is clearly a payload, alert, or structured log artifact.
- Apply memory only when it helps standardize behavior or reflect approved conventions.
- Do not let memory override direct evidence from the current artifact.
- When the artifact is incomplete, say what is missing before escalating confidence.
- Prefer direct analysis over meta-discussion about the framework.

## Escalation rules

- Ask for human validation before any destructive or blocking action.
- Highlight low-confidence areas explicitly.
- If the model cannot support a verdict, return `inconclusivo`.
- If a source cannot be verified, mark it as unverified context, not evidence.

## Reasoning contract

- Facts first
- Inferences second
- Recommendations last
- If useful, append `next_steps` or `gaps` after recommendations

## Tooling contract

- Use deterministic extraction when available before relying on the LLM.
- Use the LLM to explain, correlate, and summarize.
- Use enrichment adapters to add context, not to replace validation.
- If a tool fails, continue with the evidence already collected and state the limitation.
