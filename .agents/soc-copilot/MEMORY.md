# MEMORY

## Stable conventions

- Prefer PT-BR for the final answer.
- Prefer JSON-compatible structures for machine-readable outputs.
- Distinguish fact, inference, and recommendation.
- When possible, include MITRE ATT&CK technique IDs only if the evidence supports them.

## Analyst-facing conventions

- `summary` should be concise and technical.
- `confidence` should reflect the quality of evidence, not the confidence of wording.
- `recommended_actions` should be practical and sequenced.

## Notes

- This file should contain approved conventions and recurring patterns.
- It should not become a dump of session history.
- Case-specific memory belongs in application storage, not here.
