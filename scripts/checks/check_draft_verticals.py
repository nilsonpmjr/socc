"""
Valida a verticalizacao textual do draft por familia de telemetria.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from socc.core.engine import analyze_payload

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


def render(payload_text: str, classificacao: str = "TP") -> str:
    result = analyze_payload(payload_text=payload_text, include_draft=True, classificacao=classificacao)
    return result.get("draft", "")


try:
    email_draft = render(
        '{"sender.address":"phish@example.com","recipient.address":"victim@example.org","subject":"Invoice","url.full":"https://evil.example.com/login","authentication.result":"failure","mfaUsed":"false","sourceIPAddress":"198.51.100.77"}'
    )
    check("draft_vertical_email_label", "Recorte Analítico: Email e Identidade" in email_draft)
    check("draft_vertical_email_detail", "E-mail Remetente: phish@example.com" in email_draft)
except Exception as exc:
    check("draft_vertical_email_flow", False, str(exc))


try:
    endpoint_draft = render(
        '{"process.name":"powershell.exe","process.command_line":"powershell.exe -enc AAAA","registry.path":"HKCU\\\\Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Run\\\\Updater","fileHash":"1e8a68027db8e05c87e795c65acfa76b"}'
    )
    check("draft_vertical_endpoint_label", "Recorte Analítico: Endpoint e Execução" in endpoint_draft)
    check("draft_vertical_endpoint_detail", "Linha de Comando: powershell.exe -enc AAAA" in endpoint_draft)
except Exception as exc:
    check("draft_vertical_endpoint_flow", False, str(exc))


try:
    cloud_draft = render(
        '{"accountId":"123456789012","resourceId":"i-0abc123","roleArn":"arn:aws:iam::123456789012:role/Admin","cloud.region":"us-east-1","sourceIPAddress":"198.51.100.77"}'
    )
    check("draft_vertical_cloud_label", "Recorte Analítico: Cloud e Identidade" in cloud_draft)
    check("draft_vertical_cloud_detail", "Cloud Recurso: i-0abc123" in cloud_draft)
except Exception as exc:
    check("draft_vertical_cloud_flow", False, str(exc))


try:
    k8s_draft = render(
        '{"kubernetes.pod.name":"frontend-abc","kubernetes.namespace":"prod","container.id":"docker://abc123","container.image.name":"nginx:1.27","kubernetes.cluster.name":"cluster-east"}'
    )
    check("draft_vertical_k8s_label", "Recorte Analítico: Kubernetes e Containers" in k8s_draft)
    check("draft_vertical_k8s_detail", "Kubernetes Pod: frontend-abc" in k8s_draft)
except Exception as exc:
    check("draft_vertical_k8s_flow", False, str(exc))


try:
    network_draft = render(
        '{"src_ip":"10.0.0.5","dst_ip":"198.51.100.90","bytes_in":512,"bytes_out":4096,"network.direction":"outbound","nat.source.ip":"10.0.0.5","nat.destination.ip":"198.51.100.90","protocol":"tcp","dstport":443}'
    )
    check("draft_vertical_network_label", "Recorte Analítico: Fluxo de Rede" in network_draft)
    check("draft_vertical_network_detail", "Bytes de Saída: 4096" in network_draft or "Bytes de Saida: 4096" in network_draft)
    check("draft_vertical_network_operational_route", "Destino Operacional: Abertura de alerta" in network_draft)
except Exception as exc:
    check("draft_vertical_network_flow", False, str(exc))


try:
    fp_draft = render(
        '{"src_ip":"10.0.0.5","dst_ip":"198.51.100.90","action":"allow","http.host":"intranet.local","url.full":"https://intranet.local/health"}'
        ,
        classificacao="FP",
    )
    check("draft_fp_operational_route", "Destino Operacional: Correção de detecção" in fp_draft)
    check("draft_fp_operational_summary", "Resumo Operacional:" in fp_draft)
except Exception as exc:
    check("draft_fp_flow", False, str(exc))


print(f"\n{'='*60}")
print(f"SOC Copilot — Draft Verticals  ({len(resultados)} checks)")
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
