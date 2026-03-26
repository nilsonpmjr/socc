---
name: suspicious-url
description: |
  Specialized SOC Copilot skill for analyzing suspicious URLs, domains, redirect patterns, typo-squatting,
  and web-delivered indicators.
  Use when the primary artifact is a URL, domain, or web destination.
---

# Suspicious URL

Focused workflow for web indicators and suspicious destinations.

## When to Use

- primary artifact is a URL, domain, or redirect chain
- user asks whether a link is suspicious
- the input contains obvious web navigation or destination details

## Workflow

### 1. Parse the web artifact

- extract scheme, domain, subdomain, path, parameters, and visible redirect clues
- note encoding, shortening, impersonation, or typo-squatting patterns

### 2. Evaluate risk indicators

- identify suspicious hosting, deceptive pathing, brand impersonation, and unusual parameter usage
- separate structural risk from reputation-based claims

### 3. Determine verdict carefully

Read [`../../references/evidence-rules.md`](../../references/evidence-rules.md).

- determine whether the URL is suspicious, malicious, benign, or inconclusive
- explain what part of the URL or context supports that conclusion

### 4. Recommend safe validation

- suggest sandboxing, proxy validation, DNS checks, or user notification where appropriate
- avoid encouraging unsafe live-click validation

## Output Contract

Read [`../../references/output-contract.md`](../../references/output-contract.md).

## Guardrails

- Do not claim malicious reputation without an actual lookup.
- Make conditional statements explicit when the conclusion depends on missing context.
- Keep the advice safe for analysts and end users.
