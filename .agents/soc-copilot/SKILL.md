---
name: soc-copilot
description: |
  SOC analyst copilot for payload triage, phishing analysis, suspicious URL review, and malware behavior assessment.
  Use when analyzing security artifacts in SOCC and when a structured, evidence-based response is needed.
---

# SOC Copilot

Top-level orchestration skill for the SOCC analyst assistant.

## When to Use

- triaging payloads, alerts, suspicious snippets, or mixed security artifacts
- analyzing suspicious emails, URLs, or host-behavior clues
- generating structured security analysis for analysts
- selecting a specialized SOC playbook based on artifact type

## Load Order

1. Base identity from `identity.md`
2. Core behavior from `SOUL.md`
3. Orchestration rules from `AGENTS.md`
4. Stable conventions from `MEMORY.md`
5. Tool availability from `TOOLS.md`
6. Skill selection guidance from `skills.md`
7. One specialized skill from `skills/<name>/SKILL.md`

## Skill Selection

Use `skills.md` to choose the best specialized skill:

- `payload-triage`
- `phishing-analysis`
- `malware-behavior`
- `suspicious-url`

## Shared References

Load only what is needed:

- `references/output-contract.md` for response schema discipline
- `references/evidence-rules.md` for verdict and confidence rules
- `references/ioc-extraction.md` for extraction guidance
- `references/mitre-guidance.md` for ATT&CK enrichment discipline

## Guardrails

- Keep the response evidence-based and operational.
- Prefer one specialized skill at a time.
- Do not let prompt structure replace deterministic backend validation.
