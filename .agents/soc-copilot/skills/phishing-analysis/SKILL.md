---
name: phishing-analysis
description: |
  Specialized SOC Copilot skill for analyzing suspicious emails, headers, senders, embedded links, and attachment clues.
  Use when the user wants phishing triage or the artifact clearly contains email context.
---

# Phishing Analysis

Focused workflow for phishing and email-borne social engineering analysis.

## When to Use

- input contains sender, recipient, headers, subject, message body, or attachment details
- user asks whether a message is phishing
- links inside an email are central to the analysis

## Workflow

### 1. Identify email evidence

- extract sender, reply-to, recipient, domains, URLs, attachment names, and mail-routing clues when present
- distinguish message content from transport metadata

### 2. Evaluate phishing indicators

- look for sender and domain mismatch
- inspect suspicious links, urgent requests, spoofing language, and attachment risk
- weigh header or link mismatch more heavily than tone alone

### 3. Assess likely abuse pattern

Read [`../../references/evidence-rules.md`](../../references/evidence-rules.md) for verdict discipline.

- determine whether the artifact supports phishing, impersonation, malware delivery, or remains inconclusive
- explain why the evidence supports that conclusion

### 4. Recommend safe handling

- propose safe validation steps
- suggest reporting, isolation, or user outreach when justified

## Output Contract

Read [`../../references/output-contract.md`](../../references/output-contract.md).

## Guardrails

- Do not mark an email as phishing based only on generic urgency language.
- Separate visible evidence from reputation-dependent conclusions.
- If no header evidence exists, state that limitation clearly.
