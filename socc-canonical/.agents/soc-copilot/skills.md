# skills

## Active playbooks

- `soc-generalist`: fluxo padrão para perguntas operacionais, triagem ampla, hunting, enriquecimento e priorização
- `payload-triage`: fluxo para payloads, alertas, eventos estruturados, logs e artefatos mistos
- `phishing-analysis`: fluxo para e-mail, engenharia social, remetente, cabeçalhos e anexos
- `malware-behavior`: fluxo para execução, persistência, cadeia de processo e comportamento suspeito em host
- `suspicious-url`: fluxo para URLs, domínios, redirects, landing pages e indicadores web

## Selection guidance

- Use `soc-generalist` when the analyst asks an open-ended operational question, wants investigative help, or references IOC, CVE, ATT&CK, hunting, detection, behavior, correlation, risk, or prioritization without a clearly dominant artifact family.
- Use `suspicious-url` when the primary artifact is a URL, domain, redirect chain, or web destination under review.
- Use `phishing-analysis` when the input contains sender, recipient, subject, body, header, attachment, or mail flow context.
- Use `malware-behavior` when the input centers on execution, persistence, process tree, registry, script behavior, or host-level traces.
- Use `payload-triage` when the input is mainly a payload, alert body, event JSON, log bundle, SIEM record, or mixed structured artifact.

## Resolution policy

- Prefer one primary skill per answer.
- If the artifact overlaps multiple skills, choose the one that best matches the dominant question.
- Fall back to `soc-generalist` when classification is ambiguous.
- Do not force a specialized skill just because one keyword matched.

## Structure

Shared guidance stays under `references/` and should only be loaded when needed by the current artifact.
