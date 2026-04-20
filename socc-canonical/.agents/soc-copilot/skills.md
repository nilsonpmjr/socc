# skills

## Active playbooks

- `soc-generalist`: default workflow for day-to-day SOC conversation, investigative questions, IOC/CVE/hash lookups, detection reasoning, and natural-language guidance
- `payload-triage`: default workflow for generic payloads, logs, and suspicious artifacts
- `phishing-analysis`: specialized workflow for email and social engineering artifacts
- `malware-behavior`: specialized workflow for process execution, persistence, and malware behavior clues
- `suspicious-url`: specialized workflow for URLs, domains, redirects, and web indicators

## Selection guidance

- Use `soc-generalist` when the analyst is asking an open-ended operational question, wants help investigating, or references CVE, hash, IOC, ATT&CK, hunting, detection, behavior, correlation, or prioritization without a clearly structured artifact.
- Use `suspicious-url` when the primary artifact is a URL, domain, or redirect chain.
- Use `phishing-analysis` when the input contains sender, recipient, message body, subject, headers, or attachment context.
- Use `malware-behavior` when the input contains command lines, process trees, registry changes, persistence, or execution chains.
- Use `payload-triage` when the input is clearly a payload, alert, or structured log/event body.

## Structure

Each skill lives in its own folder under `skills/<skill-name>/SKILL.md`, following the same modular pattern used by the shared workspace skills. Shared guidance stays under `references/` to keep each skill concise.
