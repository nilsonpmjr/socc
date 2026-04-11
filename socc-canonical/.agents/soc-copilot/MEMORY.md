# MEMORY

## Stable conventions

- Prefer PT-BR for the final answer.
- Prefer JSON-compatible structures for machine-readable outputs.
- Distinguish fact, inference, and recommendation.
- When possible, include MITRE ATT&CK technique IDs only if the evidence supports them.
- Prefer explicit confidence labels when the answer contains a verdict.
- Prefer defanged output for URLs/domains only when the user asks for sharing-safe output.

## Analyst-facing conventions

- `summary` should be concise and technical.
- `confidence` should reflect the quality of evidence, not the confidence of wording.
- `recommended_actions` should be practical and sequenced.
- `observed` should contain only directly supported findings.
- `inferred` should explain why the inference is plausible.
- `gaps` should list what is missing to move from suspeito/inconclusivo to a stronger verdict.

## Notes

- This file should contain approved conventions and recurring patterns.
- It should not become a dump of session history.
- Case-specific memory belongs in application storage, not here.
- This file should stay small and stable; operational playbooks belong elsewhere.
