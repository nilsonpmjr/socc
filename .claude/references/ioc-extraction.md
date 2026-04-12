# IOC Extraction Guidance

Common observable types:

- IP addresses
- domains and subdomains
- URLs
- email addresses
- file names and paths
- hashes
- process names and command lines
- registry keys and values

Extraction rules:

- Preserve original formatting when useful for analyst review
- Strip obvious punctuation artifacts around values
- Do not normalize away meaningful path or parameter details
- Record short context showing where the IOC came from

Do not:

- infer hashes that are not present
- invent domains from brand names alone
- promote a generic string to IOC status without supporting context
