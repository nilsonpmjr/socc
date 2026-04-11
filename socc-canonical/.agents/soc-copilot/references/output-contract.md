# Output Contract

Every SOC Copilot skill should target the same structured response contract.

Required fields:

- `summary`
- `verdict`
- `confidence`
- `iocs`
- `ttps`
- `risk_reasons`
- `recommended_actions`
- `sources`

Rules:

- `summary` should be concise and technical.
- `verdict` must be one of `benigno`, `suspeito`, `malicioso`, `inconclusivo`.
- `confidence` is a value from 0 to 1 and must reflect evidence quality.
- `iocs` should include only artifacts actually observed or clearly derived from observed data.
- `ttps` should be included only when evidence supports them.
- `risk_reasons` should justify the verdict.
- `recommended_actions` should be practical and ordered.
- `sources` should identify enrichment inputs or explicitly say when no external source was used.

Response discipline:

- Put facts before inferences.
- If evidence is insufficient, choose `inconclusivo`.
- Never fabricate ATT&CK mappings, IOC reputation, CVEs, or malware family names.
