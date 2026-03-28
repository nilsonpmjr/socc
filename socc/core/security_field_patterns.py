from __future__ import annotations


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


# Catalogo pragmatico de aliases comuns em payloads de seguranca.
# Ele cobre familias recorrentes de EDR, NDR, IDS/IPS, SIEM, WAF, IAM e cloud:
# FortiGate, Palo Alto, Defender, Sentinel, CrowdStrike, Zeek, Suricata/Snort,
# Elastic/Wazuh, Trend, Cisco, Okta, GuardDuty, Chronicle e eventos ECS/OTel.
SECURITY_JSON_FIELD_PATTERNS: dict[str, list[str]] = {
    "Horario": _unique([
        "CreationTime", "StartTime", "LogTime", "time", "Timestamp", "timestamp",
        "datetime", "Time", "EventTime", "date", "@timestamp", "event.created",
        "event.ingested", "eventTime", "deviceTime", "rt", "start", "occurredAt",
    ]),
    "Usuario": _unique([
        "UserId", "Username", "User", "UserName", "user", "AccountName",
        "SamAccountName", "InitiatingUserName", "SourceUser", "usrName",
        "TargetUserName", "NetworkAccountName", "srcuser", "dstuser",
        "SubjectUserName", "TargetUser", "user.name", "user.id", "user.email",
        "userPrincipalName", "principalUserName", "account", "account_name",
        "actor.user.name", "actor.alternateId", "principal.name", "principal.user.userid",
        "initiatingProcessAccountName", "suser", "duser",
    ]),
    "IP_Origem": _unique([
        "ClientIP", "SourceIP", "SourceIp", "src_ip", "sourceip", "CallerIpAddress",
        "IpAddress", "RemoteIP", "src", "Source IP", "srcip", "SourceAddress",
        "source.ip", "client.ip", "srcaddr", "sourceAddress", "sourceIPAddress",
        "ipAddress", "remote.ip", "network.client.ip", "network.src.ip",
        "event.src.ip", "observer.ingress.ip", "principal.ip", "initiatorIp",
        "initiatingProcessRemoteSessionIP", "RemoteAddress",
    ]),
    "IP_Destino": _unique([
        "DestinationIp", "DestinationIP", "dst_ip", "TargetIP", "Destination IP",
        "dstip", "dst", "destination.ip", "dstaddr", "dest_ip", "destinationIP",
        "destinationIPAddress", "network.dst.ip", "server.ip", "event.dst.ip",
        "observer.egress.ip", "target.ip", "destinationAddress", "remoteAddress",
    ]),
    "Destino": _unique([
        "DestinationIp", "DestinationIP", "dst_ip", "ObjectId", "Destination",
        "TargetIP", "RequestURL", "Destination IP", "HostUrl", "dstip", "hostname",
        "URL", "url", "dst", "destination.ip", "destination.url", "dest_ip",
        "destinationIPAddress", "destination.domain", "host.name", "server.ip",
        "serverName", "server.name", "target.host",
    ]),
    "Hostname": _unique([
        "hostname", "host", "host.name", "ComputerName", "computer_name",
        "DeviceName", "device_name", "device.hostname", "agent.hostname",
        "endpoint.name", "endpoint.hostname", "destinationHostName", "dest_host",
        "dhost", "sourceHostName", "src_host", "shost", "dns.hostname",
        "observer.hostname", "client.hostname",
    ]),
    "Servidor": _unique([
        "server", "serverName", "server.name", "server_name", "serverHost",
        "server.host", "serverHostname", "server_host_name", "appliance",
        "sensor", "observer.name", "observer.hostname", "deviceExternalId",
    ]),
    "Caminho": _unique([
        "FilePath", "Directory", "Path", "ObjectName", "TargetObject",
        "CommandLine", "File Name", "FolderPath", "url", "file.path",
        "file.target_path", "target.file.path", "process.command_line",
        "process.executable", "Image", "ImagePath", "TargetFilename",
        "object.path", "registry.path",
    ]),
    "Arquivo": _unique([
        "FileName", "file.name", "fileName", "filename", "TargetFilename",
        "File Name", "object.file.name", "TargetObject", "ImageLoaded",
        "process.name", "ProcessName", "Image", "artifact.name",
    ]),
    "Hash_Observado": _unique([
        "sha256", "sha1", "md5", "hash", "fileHash", "FileHash",
        "file.hash", "file.hash.sha256", "file.hash.sha1", "file.hash.md5",
        "process.hash.sha256", "process.hash.sha1", "process.hash.md5",
        "TargetFileHash", "artifact.hash", "indicator.hash",
    ]),
    "LogSource": _unique([
        "LogSource", "Workload", "Category", "source", "DeviceName",
        "ComputerName", "Log Source", "devname", "hostname", "vendor",
        "product", "eventSource", "observer.name", "observer.product",
        "observer.type", "telemetry_source",
    ]),
    "Assunto": _unique([
        "ItemName", "Subject", "FileName", "ProcessName", "TaskName",
        "RuleName", "title", "Event Name", "attack", "msg", "signature",
        "alert.signature", "rule.name", "eventName", "event_type",
    ]),
    "Acao": _unique([
        "action", "Action", "EventAction", "ActionType", "event.action",
        "disposition", "outcome", "deviceAction", "response.action",
    ]),
    "Protocolo": _unique([
        "proto", "protocol", "Protocol", "network.transport", "transport",
    ]),
    "Porta_Origem": _unique([
        "srcport", "SourcePort", "sourcePort", "source.port", "src_port",
        "client.port", "network.src.port",
    ]),
    "Porta_Destino": _unique([
        "dstport", "DestinationPort", "destinationport", "PortaDestino",
        "destinationPort", "destination.port", "dst_port", "server.port",
        "network.dst.port", "target.port",
    ]),
    "Email_Remetente": _unique([
        "from", "mail.from", "sender", "sender.address", "email.from.address",
        "message.from", "smtp.mailfrom", "source.user.email",
    ]),
    "Email_Destinatario": _unique([
        "to", "recipient", "recipient.address", "email.to.address",
        "message.to", "smtp.rcptto", "destination.user.email",
    ]),
    "Email_ReplyTo": _unique([
        "reply-to", "reply_to", "replyTo", "email.reply_to.address",
        "message.reply_to",
    ]),
    "Email_Assunto": _unique([
        "subject", "email.subject", "mail.subject", "message.subject",
    ]),
    "Resultado_Autenticacao": _unique([
        "auth_result", "auth.result", "authentication.result", "outcome.reason",
        "status", "result", "signin_result", "login_result",
    ]),
    "MFA_Status": _unique([
        "mfa", "mfa_status", "mfa.result", "authentication.mfa", "is_mfa",
        "mfaRequired", "mfaUsed",
    ]),
    "Sessao_ID": _unique([
        "sessionId", "auth.session_id", "login.session_id", "session.id",
        "session_id", "session", "network.session_id",
    ]),
    "Tipo_Logon": _unique([
        "logon_type", "logonType", "login_type", "authentication.type",
        "event.login_type",
    ]),
    "DNS_Consulta": _unique([
        "query", "dns.question.name", "dns.question.registered_domain",
        "dns.qname", "qname", "rrname", "dns.query", "domainName",
    ]),
    "HTTP_Host": _unique([
        "http.host", "host.header", "url.domain", "request.host", "host_header",
        "http.request.headers.host",
    ]),
    "URL_Completa": _unique([
        "url.full", "request.url", "http.url", "uri", "request_uri",
        "full_url", "url.original",
    ]),
    "User_Agent": _unique([
        "user_agent", "user.agent", "http.user_agent", "http.request.headers.user-agent",
        "request.user_agent",
    ]),
    "TLS_SNI": _unique([
        "tls.sni", "server_name", "serverNameIndication", "tls.server_name",
        "network.tls.server_name",
    ]),
    "TLS_JA3": _unique([
        "ja3", "tls.ja3", "network.tls.ja3", "fingerprint.ja3",
    ]),
    "TLS_JA3S": _unique([
        "ja3s", "tls.ja3s", "network.tls.ja3s", "fingerprint.ja3s",
    ]),
    "Certificado_Assunto": _unique([
        "certificate.subject", "tls.server.x509.subject", "x509.subject",
        "tls.certificate.subject", "cert.subject",
    ]),
    "Processo": _unique([
        "process.name", "processName", "ProcessName", "Image", "image",
        "process.executable", "process_path",
    ]),
    "Processo_Pai": _unique([
        "process.parent.name", "parent_process_name", "ParentProcessName",
        "parent.image", "process.parent.executable",
    ]),
    "Linha_De_Comando": _unique([
        "command_line", "CommandLine", "process.command_line", "cmdline",
        "parentCommandLine", "ImageCommandLine",
    ]),
    "Registro": _unique([
        "registry.path", "registry.key", "registryKey", "TargetObject",
        "reg.path", "registry.value.path",
    ]),
    "Servico": _unique([
        "service.name", "serviceName", "ServiceName", "winlog.event_data.ServiceName",
        "service", "service.display_name",
    ]),
    "Modulo": _unique([
        "module", "module.name", "dll", "ImageLoaded", "loaded_module",
        "file.module",
    ]),
    "Cloud_Conta_ID": _unique([
        "accountId", "account.id", "cloud.account.id", "recipientAccountId",
        "aws.account.id", "gcp.project.number", "subscriptionId",
    ]),
    "Cloud_Regiao": _unique([
        "region", "cloud.region", "awsRegion", "azure.region", "gcp.region",
        "location",
    ]),
    "Cloud_Recurso": _unique([
        "resourceId", "resource.id", "cloud.resource.id", "instanceId",
        "targetResourceName", "resource.name",
    ]),
    "Cloud_Papel": _unique([
        "role", "roleArn", "role_name", "cloud.role", "principal.role",
        "userIdentity.sessionContext.sessionIssuer.userName",
    ]),
    "Cloud_Tenant_ID": _unique([
        "tenantId", "tenant.id", "azure.tenant_id", "organizationId",
    ]),
    "Cloud_Projeto_ID": _unique([
        "project.id", "projectId", "gcp.project.id", "workspaceId",
    ]),
    "Bytes_Entrada": _unique([
        "bytes_in", "network.bytes_in", "source.bytes", "inboundBytes",
        "bytesReceived", "received.bytes",
    ]),
    "Bytes_Saida": _unique([
        "bytes_out", "network.bytes_out", "destination.bytes", "outboundBytes",
        "bytesSent", "sent.bytes",
    ]),
    "Pacotes_Entrada": _unique([
        "packets_in", "source.packets", "inboundPackets", "network.packets_in",
    ]),
    "Pacotes_Saida": _unique([
        "packets_out", "destination.packets", "outboundPackets", "network.packets_out",
    ]),
    "Direcao_Rede": _unique([
        "direction", "network.direction", "flow.direction", "traffic.direction",
    ]),
    "NAT_IP_Origem": _unique([
        "nat.source.ip", "nat.src", "src_translated_ip", "source.nat.ip",
    ]),
    "NAT_IP_Destino": _unique([
        "nat.destination.ip", "nat.dst", "dst_translated_ip", "destination.nat.ip",
    ]),
    "Sessao_Rede_ID": _unique([
        "network.session_id", "sessionid", "session_id", "flow.id", "connection.id",
    ]),
    "Zona_Rede": _unique([
        "zone", "srczone", "dstzone", "network.zone", "security_zone",
    ]),
    "Interface_Rede": _unique([
        "interface", "srcintf", "dstintf", "observer.interface.name", "network.interface",
    ]),
    "Kubernetes_Pod": _unique([
        "kubernetes.pod.name", "k8s.pod.name", "pod.name", "pod",
    ]),
    "Kubernetes_Namespace": _unique([
        "kubernetes.namespace", "k8s.namespace.name", "namespace", "namespace_name",
    ]),
    "Container_ID": _unique([
        "container.id", "kubernetes.container.id", "docker.container.id", "containerId",
    ]),
    "Container_Imagem": _unique([
        "container.image.name", "container.image.tag", "image", "image.name",
        "kubernetes.container.image",
    ]),
    "Kubernetes_Node": _unique([
        "kubernetes.node.name", "k8s.node.name", "node.name", "node",
    ]),
    "Kubernetes_Cluster": _unique([
        "kubernetes.cluster.name", "k8s.cluster.name", "cluster.name", "cluster",
    ]),
    "Kubernetes_ServiceAccount": _unique([
        "kubernetes.serviceaccount.name", "serviceAccount", "serviceaccount.name",
        "k8s.service_account.name",
    ]),
    "Kubernetes_Workload": _unique([
        "kubernetes.deployment.name", "kubernetes.replicaset.name", "workload.name",
        "workload", "orchestrator.resource.name",
    ]),
}
