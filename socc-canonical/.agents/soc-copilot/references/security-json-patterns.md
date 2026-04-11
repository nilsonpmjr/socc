# Security JSON Field Patterns

Purpose:

- help the copilot recognize common aliases used by EDR, NDR, IDS/IPS, SIEM, IAM, WAF and cloud detectors
- reduce misses when important evidence appears under vendor-specific JSON keys
- treat these aliases as extraction hints, not as permission to invent facts

High-signal entities to always inspect:

- username and account identifiers
- source IP and destination IP, including IPv4 and IPv6
- hostname and server names
- file name and file path
- hashes such as MD5, SHA1 and SHA256
- ports, protocol, action, URL and domain
- e-mail headers and authentication/session fields
- process, registry, service and module telemetry
- cloud identity/resource context and Kubernetes/container metadata

Common alias families by canonical field:

- `Usuario`:
  `user`, `username`, `user.name`, `user.id`, `userPrincipalName`, `UserId`, `UserName`, `AccountName`, `SamAccountName`, `SubjectUserName`, `TargetUserName`, `srcuser`, `dstuser`, `principalUserName`, `actor.alternateId`
- `IP_Origem`:
  `srcip`, `src_ip`, `src`, `sourceip`, `source.ip`, `SourceIP`, `SourceIp`, `sourceIPAddress`, `sourceAddress`, `ClientIP`, `client.ip`, `RemoteIP`, `RemoteAddress`, `CallerIpAddress`, `event.src.ip`
- `IP_Destino`:
  `dstip`, `dst_ip`, `dst`, `destinationip`, `destination.ip`, `DestinationIP`, `DestinationIp`, `destinationIPAddress`, `destinationAddress`, `TargetIP`, `server.ip`, `event.dst.ip`
- `Hostname`:
  `hostname`, `host`, `host.name`, `ComputerName`, `DeviceName`, `device.hostname`, `agent.hostname`, `endpoint.hostname`, `destinationHostName`, `dest_host`, `dhost`
- `Servidor`:
  `server`, `serverName`, `server.name`, `server_name`, `serverHost`, `server.host`, `observer.name`, `sensor`, `appliance`
- `Arquivo`:
  `file.name`, `fileName`, `FileName`, `filename`, `TargetFilename`, `object.file.name`, `process.name`, `Image`
- `Caminho`:
  `file.path`, `FilePath`, `Path`, `Directory`, `FolderPath`, `TargetObject`, `TargetFilename`, `process.command_line`, `process.executable`, `ImagePath`
- `Hash_Observado`:
  `hash`, `sha256`, `sha1`, `md5`, `fileHash`, `FileHash`, `file.hash`, `file.hash.sha256`, `file.hash.sha1`, `file.hash.md5`, `process.hash.sha256`
- `Porta_Origem`:
  `srcport`, `SourcePort`, `sourcePort`, `source.port`, `src_port`, `network.src.port`
- `Porta_Destino`:
  `dstport`, `DestinationPort`, `destinationPort`, `destination.port`, `dst_port`, `server.port`, `network.dst.port`
- `Email_Remetente`:
  `from`, `mail.from`, `sender`, `sender.address`, `email.from.address`, `message.from`, `smtp.mailfrom`
- `Email_Destinatario`:
  `to`, `recipient`, `recipient.address`, `email.to.address`, `message.to`, `smtp.rcptto`
- `Email_ReplyTo`:
  `reply-to`, `reply_to`, `replyTo`, `email.reply_to.address`
- `Email_Assunto`:
  `subject`, `email.subject`, `mail.subject`, `message.subject`
- `Resultado_Autenticacao`:
  `auth_result`, `auth.result`, `authentication.result`, `signin_result`, `login_result`, `status`
- `MFA_Status`:
  `mfa`, `mfa_status`, `mfa.result`, `authentication.mfa`, `mfaRequired`, `mfaUsed`
- `Sessao_ID`:
  `session`, `session.id`, `session_id`, `sessionId`, `auth.session_id`, `network.session_id`
- `Tipo_Logon`:
  `logon_type`, `logonType`, `login_type`, `authentication.type`
- `DNS_Consulta`:
  `query`, `dns.question.name`, `dns.qname`, `qname`, `rrname`, `dns.query`, `domainName`
- `HTTP_Host`:
  `http.host`, `host.header`, `url.domain`, `request.host`, `host_header`
- `URL_Completa`:
  `url.full`, `request.url`, `http.url`, `uri`, `request_uri`, `url.original`
- `User_Agent`:
  `user_agent`, `user.agent`, `http.user_agent`, `request.user_agent`
- `TLS_SNI`:
  `tls.sni`, `server_name`, `serverNameIndication`, `tls.server_name`
- `TLS_JA3` / `TLS_JA3S`:
  `ja3`, `tls.ja3`, `network.tls.ja3`, `ja3s`, `tls.ja3s`, `network.tls.ja3s`
- `Certificado_Assunto`:
  `certificate.subject`, `tls.server.x509.subject`, `x509.subject`, `cert.subject`
- `Processo` / `Processo_Pai`:
  `process.name`, `processName`, `Image`, `process.executable`, `process.parent.name`, `ParentProcessName`
- `Linha_De_Comando`:
  `command_line`, `CommandLine`, `process.command_line`, `cmdline`
- `Registro`:
  `registry.path`, `registry.key`, `registryKey`, `TargetObject`
- `Servico`:
  `service.name`, `serviceName`, `ServiceName`, `service.display_name`
- `Modulo`:
  `module`, `module.name`, `dll`, `ImageLoaded`, `loaded_module`
- `Cloud_Conta_ID`:
  `accountId`, `account.id`, `cloud.account.id`, `recipientAccountId`, `subscriptionId`
- `Cloud_Regiao`:
  `region`, `cloud.region`, `awsRegion`, `azure.region`, `gcp.region`, `location`
- `Cloud_Recurso`:
  `resourceId`, `resource.id`, `cloud.resource.id`, `instanceId`, `targetResourceName`
- `Cloud_Papel`:
  `role`, `roleArn`, `role_name`, `cloud.role`, `principal.role`
- `Cloud_Tenant_ID` / `Cloud_Projeto_ID`:
  `tenantId`, `tenant.id`, `azure.tenant_id`, `project.id`, `projectId`, `gcp.project.id`
- `Bytes_Entrada` / `Bytes_Saida` / `Pacotes_Entrada` / `Pacotes_Saida`:
  `bytes_in`, `bytes_out`, `packets_in`, `packets_out`, `source.bytes`, `destination.bytes`
- `Direcao_Rede`:
  `direction`, `network.direction`, `flow.direction`, `traffic.direction`
- `NAT_IP_Origem` / `NAT_IP_Destino`:
  `nat.source.ip`, `nat.destination.ip`, `nat.src`, `nat.dst`, `source.nat.ip`, `destination.nat.ip`
- `Sessao_Rede_ID` / `Zona_Rede` / `Interface_Rede`:
  `network.session_id`, `flow.id`, `connection.id`, `zone`, `srczone`, `dstzone`, `interface`, `srcintf`, `dstintf`
- `Kubernetes_Pod` / `Kubernetes_Namespace`:
  `kubernetes.pod.name`, `k8s.pod.name`, `pod.name`, `kubernetes.namespace`, `k8s.namespace.name`
- `Container_ID` / `Container_Imagem`:
  `container.id`, `docker.container.id`, `container.image.name`, `container.image.tag`
- `Kubernetes_Node` / `Kubernetes_Cluster`:
  `kubernetes.node.name`, `k8s.node.name`, `kubernetes.cluster.name`, `k8s.cluster.name`
- `Kubernetes_ServiceAccount` / `Kubernetes_Workload`:
  `kubernetes.serviceaccount.name`, `serviceAccount`, `kubernetes.deployment.name`, `workload.name`

Detector families where these aliases commonly appear:

- FortiGate, Palo Alto, Check Point, Cisco, Juniper
- CrowdStrike, Defender for Endpoint, SentinelOne, Carbon Black, Trend Micro
- Suricata, Snort, Zeek, Security Onion
- Microsoft Sentinel, Elastic, Wazuh, Splunk, QRadar, Chronicle
- Okta, Entra ID, Active Directory, Google Workspace, AWS GuardDuty
- CloudTrail, GuardDuty, Azure AD/Entra, GCP Audit Logs, Prisma, Wiz
- Kubernetes Audit Logs, Falco, Sysdig, Aqua, Datadog, EKS/GKE/AKS

Extraction discipline:

- prefer exact values present in normalized fields or raw payload
- if a field is absent, leave it empty rather than guessing
- accept IPv6 as first-class evidence, not only IPv4
- when both hostname and destination IP exist, keep both if possible
- when a hash is present, preserve full value without truncation in structured data
- when a file name and a path both exist, keep the path in `Caminho` and the best file indicator in `Arquivo`
- when URL, DNS, HTTP host and SNI coexist, keep the most specific value in its own field and avoid collapsing them prematurely
- when cloud or Kubernetes metadata exists, preserve tenancy, resource and workload context because it often changes incident scope
