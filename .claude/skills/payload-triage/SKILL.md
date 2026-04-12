---
name: payload-triage
description: |
  Default SOC Copilot skill for analyzing raw payloads, mixed artifacts, suspicious snippets, and generic alerts.
  Use when the artifact type is unknown or when no specialized skill is a better fit.
---

# Payload Triage

Default analysis workflow for raw or mixed security artifacts.

## When to Use

- artifact type is unknown
- input is a raw payload, alert body, suspicious snippet, or mixed text
- no specialized playbook is clearly a better match

## Workflow

### 1. Establish the artifact context

- identify whether the input looks like log data, command content, email text, URL-heavy content, or generic payload
- note missing context that limits confidence

### 2. Extract observable evidence

Read [`../../references/ioc-extraction.md`](../../references/ioc-extraction.md) when extraction details matter.

- identify visible IOCs
- capture suspicious strings, commands, or infrastructure hints
- keep direct observations separate from assumptions

### 3. Assess likely risk

Read [`../../references/evidence-rules.md`](../../references/evidence-rules.md) for verdict and confidence guidance.

- determine whether the artifact is benign, suspicious, malicious, or inconclusive
- justify the verdict with explicit risk reasons

### 4. Suggest next analyst actions

- prioritize low-risk validation steps first
- recommend containment only when supported by evidence

## Output Contract

Read [`../../references/output-contract.md`](../../references/output-contract.md).

## Guardrails

- Do not force ATT&CK mapping for weak evidence.
- Prefer `inconclusivo` over false precision.
- Keep the result operational and concise.
