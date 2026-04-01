"""
Valida aliases ampliados de campos JSON de seguranca e suporte a IPv6.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from socc.core import input_adapter, parser

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


try:
    payload_nested = """
    {
      "event": {"created": "2026-03-18T22:04:30Z", "action": "blocked"},
      "user": {"name": "alice@example.com"},
      "source": {"ip": "2606:4700:4700::1111", "port": 51515},
      "destination": {"ip": "2001:4860:4860::8888", "port": 443, "domain": "api.example.org"},
      "host": {"name": "endpoint-01"},
      "server": {"name": "mail-gw-01"},
      "file": {
        "name": "invoice.exe",
        "path": "C:\\\\Users\\\\Public\\\\invoice.exe",
        "hash": {"sha256": "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f"}
      }
    }
    """
    fmt_nested, raw_fields_nested, _ = input_adapter.adapt(payload_nested)
    parsed_nested = parser.parse_payload(payload_nested, raw_fields=raw_fields_nested)
    nested_iocs = parsed_nested.get("IOCs", {})

    check("security_patterns_nested_json_format", fmt_nested == "json")
    check("security_patterns_nested_user", parsed_nested.get("Usuario") == "alice@example.com")
    check("security_patterns_nested_src_ipv6", parsed_nested.get("IP_Origem") == "2606:4700:4700::1111")
    check("security_patterns_nested_dst_ipv6", parsed_nested.get("IP_Destino") == "2001:4860:4860::8888")
    check("security_patterns_nested_hostname", parsed_nested.get("Hostname") == "endpoint-01")
    check("security_patterns_nested_server", parsed_nested.get("Servidor") == "mail-gw-01")
    check("security_patterns_nested_file_name", parsed_nested.get("Arquivo") == "invoice.exe")
    check("security_patterns_nested_file_path", parsed_nested.get("Caminho") == "C:\\Users\\Public\\invoice.exe")
    check(
        "security_patterns_nested_hash",
        parsed_nested.get("Hash_Observado") == "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f",
    )
    check(
        "security_patterns_nested_ioc_ipv6",
        {"2606:4700:4700::1111", "2001:4860:4860::8888"}.issubset(set(nested_iocs.get("ips_externos", []))),
    )
    check(
        "security_patterns_nested_ioc_hash",
        "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f" in nested_iocs.get("hashes", []),
    )
except Exception as exc:
    check("security_patterns_nested_flow", False, str(exc))


try:
    payload_flat = """
    {
      "userPrincipalName": "bob@example.com",
      "sourceIPAddress": "203.0.113.7",
      "destinationIPAddress": "198.51.100.8",
      "destinationHostName": "db01.corp.example",
      "serverHost": "proxy01.corp.example",
      "TargetFilename": "payload.dll",
      "fileHash": "1e8a68027db8e05c87e795c65acfa76b",
      "srcport": 12345,
      "dstport": 3389
    }
    """
    fmt_flat, raw_fields_flat, _ = input_adapter.adapt(payload_flat)
    parsed_flat = parser.parse_payload(payload_flat, raw_fields=raw_fields_flat)

    check("security_patterns_flat_json_format", fmt_flat == "json")
    check("security_patterns_flat_user", parsed_flat.get("Usuario") == "bob@example.com")
    check("security_patterns_flat_src_ipv4", parsed_flat.get("IP_Origem") == "203.0.113.7")
    check("security_patterns_flat_dst_ipv4", parsed_flat.get("IP_Destino") == "198.51.100.8")
    check("security_patterns_flat_hostname", parsed_flat.get("Hostname") == "db01.corp.example")
    check("security_patterns_flat_server", parsed_flat.get("Servidor") == "proxy01.corp.example")
    check("security_patterns_flat_file", parsed_flat.get("Arquivo") == "payload.dll")
    check("security_patterns_flat_hash", parsed_flat.get("Hash_Observado") == "1e8a68027db8e05c87e795c65acfa76b")
    check("security_patterns_flat_src_port", parsed_flat.get("Porta_Origem") == "12345")
    check("security_patterns_flat_dst_port", parsed_flat.get("Porta_Destino") == "3389")
except Exception as exc:
    check("security_patterns_flat_flow", False, str(exc))

try:
    payload_extended = """
    {
      "sender.address": "phish@example.com",
      "recipient.address": "victim@example.org",
      "replyTo": "reply@example.com",
      "subject": "Reset your password",
      "authentication.result": "failure",
      "mfaUsed": "true",
      "sessionId": "sess-123",
      "logonType": "3",
      "dns.question.name": "evil.example.com",
      "http.host": "portal.example.com",
      "url.full": "https://portal.example.com/login",
      "http.user_agent": "curl/8.7.1",
      "tls.sni": "portal.example.com",
      "ja3": "771,4865-4866-4867,0-11-10,23-24,0",
      "ja3s": "771,4865,23,0",
      "certificate.subject": "CN=portal.example.com",
      "process.name": "powershell.exe",
      "process.parent.name": "winword.exe",
      "process.command_line": "powershell.exe -enc AAAA",
      "registry.path": "HKCU\\\\Software\\\\Bad",
      "service.name": "WinUpdate",
      "module.name": "evil.dll",
      "accountId": "123456789012",
      "cloud.region": "us-east-1",
      "resourceId": "i-0abc123",
      "roleArn": "arn:aws:iam::123456789012:role/Admin",
      "tenantId": "tenant-42",
      "project.id": "project-red",
      "bytes_in": 2048,
      "bytes_out": 4096,
      "packets_in": 12,
      "packets_out": 18,
      "network.direction": "outbound",
      "nat.source.ip": "10.0.0.5",
      "nat.destination.ip": "198.51.100.90",
      "network.session_id": "flow-77",
      "zone": "dmz",
      "interface": "eth0",
      "kubernetes.pod.name": "nginx-7d8f9",
      "kubernetes.namespace": "prod",
      "container.id": "docker://abc123",
      "container.image.name": "nginx:1.27",
      "kubernetes.node.name": "node-a",
      "kubernetes.cluster.name": "cluster-east",
      "kubernetes.serviceaccount.name": "default",
      "kubernetes.deployment.name": "frontend"
    }
    """
    fmt_extended, raw_fields_extended, _ = input_adapter.adapt(payload_extended)
    parsed_extended = parser.parse_payload(payload_extended, raw_fields=raw_fields_extended)

    check("security_patterns_extended_json_format", fmt_extended == "json")
    check("security_patterns_extended_email_from", parsed_extended.get("Email_Remetente") == "phish@example.com")
    check("security_patterns_extended_email_to", parsed_extended.get("Email_Destinatario") == "victim@example.org")
    check("security_patterns_extended_email_replyto", parsed_extended.get("Email_ReplyTo") == "reply@example.com")
    check("security_patterns_extended_email_subject", parsed_extended.get("Email_Assunto") == "Reset your password")
    check("security_patterns_extended_auth_result", parsed_extended.get("Resultado_Autenticacao") == "failure")
    check("security_patterns_extended_mfa", parsed_extended.get("MFA_Status") == "true")
    check("security_patterns_extended_session", parsed_extended.get("Sessao_ID") == "sess-123")
    check("security_patterns_extended_logon_type", parsed_extended.get("Tipo_Logon") == "3")
    check("security_patterns_extended_dns", parsed_extended.get("DNS_Consulta") == "evil.example.com")
    check("security_patterns_extended_http_host", parsed_extended.get("HTTP_Host") == "portal.example.com")
    check("security_patterns_extended_url", parsed_extended.get("URL_Completa") == "https://portal.example.com/login")
    check("security_patterns_extended_user_agent", parsed_extended.get("User_Agent") == "curl/8.7.1")
    check("security_patterns_extended_tls_sni", parsed_extended.get("TLS_SNI") == "portal.example.com")
    check("security_patterns_extended_ja3", parsed_extended.get("TLS_JA3") == "771,4865-4866-4867,0-11-10,23-24,0")
    check("security_patterns_extended_ja3s", parsed_extended.get("TLS_JA3S") == "771,4865,23,0")
    check("security_patterns_extended_cert_subject", parsed_extended.get("Certificado_Assunto") == "CN=portal.example.com")
    check("security_patterns_extended_process", parsed_extended.get("Processo") == "powershell.exe")
    check("security_patterns_extended_parent_process", parsed_extended.get("Processo_Pai") == "winword.exe")
    check("security_patterns_extended_cmdline", parsed_extended.get("Linha_De_Comando") == "powershell.exe -enc AAAA")
    check("security_patterns_extended_registry", parsed_extended.get("Registro") == "HKCU\\Software\\Bad")
    check("security_patterns_extended_service", parsed_extended.get("Servico") == "WinUpdate")
    check("security_patterns_extended_module", parsed_extended.get("Modulo") == "evil.dll")
    check("security_patterns_extended_cloud_account", parsed_extended.get("Cloud_Conta_ID") == "123456789012")
    check("security_patterns_extended_cloud_region", parsed_extended.get("Cloud_Regiao") == "us-east-1")
    check("security_patterns_extended_cloud_resource", parsed_extended.get("Cloud_Recurso") == "i-0abc123")
    check(
        "security_patterns_extended_cloud_role",
        parsed_extended.get("Cloud_Papel") == "arn:aws:iam::123456789012:role/Admin",
    )
    check("security_patterns_extended_cloud_tenant", parsed_extended.get("Cloud_Tenant_ID") == "tenant-42")
    check("security_patterns_extended_cloud_project", parsed_extended.get("Cloud_Projeto_ID") == "project-red")
    check("security_patterns_extended_bytes_in", parsed_extended.get("Bytes_Entrada") == "2048")
    check("security_patterns_extended_bytes_out", parsed_extended.get("Bytes_Saida") == "4096")
    check("security_patterns_extended_packets_in", parsed_extended.get("Pacotes_Entrada") == "12")
    check("security_patterns_extended_packets_out", parsed_extended.get("Pacotes_Saida") == "18")
    check("security_patterns_extended_direction", parsed_extended.get("Direcao_Rede") == "outbound")
    check("security_patterns_extended_nat_src", parsed_extended.get("NAT_IP_Origem") == "10.0.0.5")
    check("security_patterns_extended_nat_dst", parsed_extended.get("NAT_IP_Destino") == "198.51.100.90")
    check("security_patterns_extended_network_session", parsed_extended.get("Sessao_Rede_ID") == "flow-77")
    check("security_patterns_extended_zone", parsed_extended.get("Zona_Rede") == "dmz")
    check("security_patterns_extended_interface", parsed_extended.get("Interface_Rede") == "eth0")
    check("security_patterns_extended_k8s_pod", parsed_extended.get("Kubernetes_Pod") == "nginx-7d8f9")
    check("security_patterns_extended_k8s_namespace", parsed_extended.get("Kubernetes_Namespace") == "prod")
    check("security_patterns_extended_container_id", parsed_extended.get("Container_ID") == "docker://abc123")
    check("security_patterns_extended_container_image", parsed_extended.get("Container_Imagem") == "nginx:1.27")
    check("security_patterns_extended_k8s_node", parsed_extended.get("Kubernetes_Node") == "node-a")
    check("security_patterns_extended_k8s_cluster", parsed_extended.get("Kubernetes_Cluster") == "cluster-east")
    check(
        "security_patterns_extended_k8s_serviceaccount",
        parsed_extended.get("Kubernetes_ServiceAccount") == "default",
    )
    check("security_patterns_extended_k8s_workload", parsed_extended.get("Kubernetes_Workload") == "frontend")
except Exception as exc:
    check("security_patterns_extended_flow", False, str(exc))


print(f"\n{'='*60}")
print(f"SOCC Runtime — Security Field Patterns  ({len(resultados)} checks)")
print("=" * 60)
falhas = [(n, d) for s, n, d in resultados if s == FAIL]
aprovados = len(resultados) - len(falhas)
print(f"  Aprovados : {aprovados}/{len(resultados)}")
print(f"  Falhas    : {len(falhas)}/{len(resultados)}")
print()
for nome, detalhe in falhas:
    extra = f" — {detalhe}" if detalhe else ""
    print(f"  FALHA: {nome}{extra}")
if not falhas:
    print("  Todos os checks passaram.")
print()

sys.exit(1 if falhas else 0)
