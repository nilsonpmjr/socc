# Telemetry Investigation Patterns

Purpose:

- transform extracted telemetry into investigation-ready context
- highlight patterns without inventing facts or forcing a final verdict
- help distinguish scope, delivery, execution, persistence and exfiltration signals

Investigation families:

- `email_auth`:
  phishing delivery, malicious attachment, malicious link, external auth pressure, MFA gap
- `dns_http_tls`:
  suspicious web channel, HTTP/TLS beaconing, anomalous DNS, possible tunneling
- `process_endpoint`:
  LOLBins, script execution, persistence via registry/service/task, suspicious module load
- `cloud_identity`:
  cloud account or role exposure, suspicious resource access, tenant or subscription relevance
- `network_flow_nat`:
  outbound asymmetry, NAT path awareness, source/destination attribution risk
- `kubernetes_container`:
  pod or namespace scope, container image relevance, service account or cluster blast radius

Discipline:

- treat these patterns as investigative context, not as a final incident decision
- prefer concrete evidence from parsed fields and raw payload over generic assumptions
- when context depends on external reputation, say that clearly
- when the telemetry only changes scope, describe scope rather than overclaiming attacker intent

Good examples:

- "Email sender + subject + URL/file suggests possible phishing delivery context."
- "External auth failures with MFA gap suggest credential pressure and justify deeper review."
- "PowerShell with encoded command suggests script execution by LOLBin and deserves EDR correlation."
- "Registry Run key or service creation suggests persistence mechanism on the endpoint."
- "High outbound bytes to external destination suggests exfiltration or anomalous upload signal."
- "Cloud resource, role and external source IP expand the blast radius to identity and control plane."
- "Pod, namespace and container image indicate workload scope in Kubernetes."
