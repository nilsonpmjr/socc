from __future__ import annotations

import ipaddress
from typing import Any


_FALSE_TOKENS = {
    "false", "0", "no", "nao", "não", "disabled", "disable", "not used",
    "unused", "absent", "off",
}
_AUTH_FAILURE_TOKENS = (
    "fail", "failure", "failed", "denied", "reject", "invalid",
    "block", "error", "unsuccess", "lockout",
)
_TI_MALICIOUS_TOKENS = (
    "malicious", "malicioso", "malware", "trojan", "botnet",
    "ransomware", "phishing", "exploit", "c2", "command and control",
)
_TI_SUSPICIOUS_TOKENS = (
    "suspicious", "suspeito", "potentially malicious", "high risk", "alto risco",
    "moderate risk", "medium risk",
)
_LOLBIN_TECHNIQUES: list[tuple[tuple[str, ...], dict[str, str]]] = [
    (("powershell", "pwsh"), {"id": "T1059.001", "reason": "Uso de PowerShell observado no payload."}),
    (("cmd.exe",), {"id": "T1059.003", "reason": "Uso de interpretador de comando do Windows observado."}),
    (("wscript", "cscript"), {"id": "T1059.005", "reason": "Uso de motor de script do Windows observado."}),
    (("mshta",), {"id": "T1218.005", "reason": "Execução por binário proxy mshta observada."}),
    (("regsvr32",), {"id": "T1218.010", "reason": "Execução por binário proxy regsvr32 observada."}),
    (("rundll32",), {"id": "T1218.011", "reason": "Execução por binário proxy rundll32 observada."}),
]


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.upper() in {"", "N/A", "NONE", "NULL"} else text


def _to_int(value: Any) -> int | None:
    try:
        if isinstance(value, bool):
            return None
        if value is None:
            return None
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _is_external_ip(value: Any) -> bool:
    text = _clean_text(value)
    if not text:
        return False
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return False
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        return False
    if ip.version == 4:
        internal_networks = (
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
            ipaddress.ip_network("127.0.0.0/8"),
            ipaddress.ip_network("169.254.0.0/16"),
        )
    else:
        internal_networks = (
            ipaddress.ip_network("fc00::/7"),
            ipaddress.ip_network("fe80::/10"),
            ipaddress.ip_network("::1/128"),
        )
    return not any(ip in network for network in internal_networks)


def _looks_false(value: Any) -> bool:
    text = _clean_text(value).lower()
    return bool(text) and text in _FALSE_TOKENS


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in tokens)


def _ti_disposition_for_value(value: Any, ti_results: dict[str, str]) -> str:
    candidate = _clean_text(value).lower()
    if not candidate:
        return ""
    for ioc, result in (ti_results or {}).items():
        ioc_text = _clean_text(ioc).lower()
        if not ioc_text:
            continue
        if candidate == ioc_text or candidate in ioc_text or ioc_text in candidate:
            result_lower = _clean_text(result).lower()
            if _contains_any(result_lower, _TI_MALICIOUS_TOKENS):
                return "malicious"
            if _contains_any(result_lower, _TI_SUSPICIOUS_TOKENS):
                return "suspicious"
            return "known"
    return ""


def _build_evidence(*items: tuple[str, Any]) -> list[str]:
    evidence: list[str] = []
    for label, value in items:
        cleaned = _clean_text(value)
        if cleaned:
            evidence.append(f"{label}: {cleaned}")
    return evidence


def _append_context(
    target: list[dict[str, Any]],
    seen: set[str],
    *,
    context_id: str,
    family: str,
    title: str,
    summary: str,
    confidence: float,
    severity: str,
    rationale: str,
    evidence: list[str],
    recommended_actions: list[str],
    mitre_techniques: list[dict[str, str]] | None = None,
) -> None:
    if context_id in seen:
        return
    seen.add(context_id)
    target.append(
        {
            "id": context_id,
            "family": family,
            "title": title,
            "summary": _clean_text(summary),
            "confidence": max(0.0, min(1.0, float(confidence))),
            "severity": severity,
            "rationale": _clean_text(rationale),
            "evidence": [item for item in evidence if _clean_text(item)],
            "recommended_actions": [
                _clean_text(item) for item in recommended_actions if _clean_text(item)
            ],
            "mitre_techniques": [
                {
                    "id": _clean_text(item.get("id")),
                    "reason": _clean_text(item.get("reason")),
                }
                for item in (mitre_techniques or [])
                if _clean_text(item.get("id"))
            ],
        }
    )


def build_security_contexts(
    fields: dict[str, Any],
    ti_results: dict[str, str] | None = None,
    raw_text: str = "",
) -> list[dict[str, Any]]:
    ti_results = ti_results or {}
    contexts: list[dict[str, Any]] = []
    seen: set[str] = set()

    email_from = fields.get("Email_Remetente")
    email_to = fields.get("Email_Destinatario")
    email_subject = fields.get("Email_Assunto")
    url = fields.get("URL_Completa")
    dns_query = fields.get("DNS_Consulta")
    http_host = fields.get("HTTP_Host")
    tls_sni = fields.get("TLS_SNI")
    file_name = fields.get("Arquivo")
    file_hash = fields.get("Hash_Observado")
    auth_result = _clean_text(fields.get("Resultado_Autenticacao"))
    mfa_status = fields.get("MFA_Status")
    source_ip = fields.get("IP_Origem")
    dest_ip = fields.get("IP_Destino")
    process_name = _clean_text(fields.get("Processo"))
    command_line = _clean_text(fields.get("Linha_De_Comando"))
    registry_path = _clean_text(fields.get("Registro"))
    service_name = _clean_text(fields.get("Servico"))
    bytes_in = _to_int(fields.get("Bytes_Entrada"))
    bytes_out = _to_int(fields.get("Bytes_Saida"))
    cloud_account = fields.get("Cloud_Conta_ID")
    cloud_resource = fields.get("Cloud_Recurso")
    cloud_role = fields.get("Cloud_Papel")
    kubernetes_pod = fields.get("Kubernetes_Pod")
    kubernetes_namespace = fields.get("Kubernetes_Namespace")
    container_id = fields.get("Container_ID")
    container_image = fields.get("Container_Imagem")
    nat_src = fields.get("NAT_IP_Origem")
    nat_dst = fields.get("NAT_IP_Destino")
    dest_port = _clean_text(fields.get("Porta_Destino"))

    if _clean_text(email_from) and (_clean_text(email_subject) or _clean_text(email_to)) and any(
        _clean_text(item) for item in (url, dns_query, http_host, file_name, file_hash)
    ):
        actions = [
            "Validar reputacao do remetente e revisar se houve entrega para outros destinatarios.",
            "Inspecionar URL, anexo e hash associados antes de qualquer liberacao operacional.",
            "Correlacionar o evento com bloqueios de e-mail, proxy e EDR do mesmo periodo.",
        ]
        mitre = [{"id": "T1566", "reason": "Evento combina remetente de e-mail com artefatos entregues ao usuario."}]
        if _clean_text(file_name):
            mitre.append({"id": "T1566.001", "reason": "Artefato de anexo observado no contexto do e-mail."})
        if _clean_text(url) or _clean_text(dns_query) or _clean_text(http_host):
            mitre.append({"id": "T1566.002", "reason": "Link ou dominio observado no contexto do e-mail."})
        _append_context(
            contexts,
            seen,
            context_id="email_phishing_delivery",
            family="email_auth",
            title="Possivel vetor de phishing",
            summary="O evento combina cabeçalhos de e-mail com link, dominio ou arquivo, sugerindo contexto de phishing ou entrega inicial.",
            confidence=0.84 if _clean_text(url) or _clean_text(file_name) else 0.76,
            severity="high",
            rationale="A combinacao de remetente, destinatario/assunto e artefato clicavel ou anexavel costuma indicar vetor inicial de phishing.",
            evidence=_build_evidence(
                ("E-mail remetente", email_from),
                ("E-mail destinatario", email_to),
                ("E-mail assunto", email_subject),
                ("URL", url),
                ("DNS", dns_query),
                ("Arquivo", file_name),
            ),
            recommended_actions=actions,
            mitre_techniques=mitre,
        )

    auth_lower = auth_result.lower()
    if auth_lower and _contains_any(auth_lower, _AUTH_FAILURE_TOKENS) and _is_external_ip(source_ip):
        confidence = 0.76 + (0.07 if _looks_false(mfa_status) else 0.0)
        _append_context(
            contexts,
            seen,
            context_id="external_auth_pressure",
            family="email_auth",
            title="Pressao de autenticacao de origem externa",
            summary="A telemetria indica falha de autenticacao associada a origem externa.",
            confidence=confidence,
            severity="high" if _looks_false(mfa_status) else "medium",
            rationale="Falhas de autenticacao vindas de IP externo aumentam a relevancia para brute force, password spray ou tentativa de uso indevido de conta.",
            evidence=_build_evidence(
                ("IP de origem", source_ip),
                ("Resultado da autenticacao", auth_result),
                ("MFA", mfa_status),
                ("Sessao", fields.get("Sessao_ID")),
                ("Tipo de logon", fields.get("Tipo_Logon")),
            ),
            recommended_actions=[
                "Correlacionar a origem com outras tentativas de autenticacao no mesmo periodo.",
                "Verificar bloqueios, desafios MFA e possivel necessidade de reset de credenciais.",
                "Revisar se a conta possui comportamento normal para a geografia e horario observados.",
            ],
            mitre_techniques=[
                {"id": "T1110", "reason": "Falha de autenticacao externa e compativel com pressao sobre credenciais."},
            ],
        )

    web_indicator = next(
        (
            value
            for value in (url, http_host, tls_sni, dns_query)
            if _clean_text(value)
        ),
        "",
    )
    web_ti = _ti_disposition_for_value(web_indicator, ti_results)
    if _clean_text(web_indicator) and (
        _clean_text(fields.get("TLS_JA3"))
        or _clean_text(fields.get("TLS_JA3S"))
        or _is_external_ip(dest_ip)
        or web_ti in {"malicious", "suspicious"}
    ):
        _append_context(
            contexts,
            seen,
            context_id="suspicious_web_channel",
            family="dns_http_tls",
            title="Canal web ou TLS relevante para investigacao",
            summary="Ha telemetria HTTP/TLS/DNS suficiente para tratar o fluxo como canal web relevante para investigacao.",
            confidence=0.8 if web_ti == "malicious" else 0.74 if web_ti == "suspicious" else 0.69,
            severity="high" if web_ti == "malicious" else "medium",
            rationale="URL, host HTTP, SNI ou dominio combinados com destino externo, fingerprint TLS ou reputacao negativa merecem analise prioritaria.",
            evidence=_build_evidence(
                ("URL", url),
                ("HTTP Host", http_host),
                ("TLS SNI", tls_sni),
                ("DNS", dns_query),
                ("JA3", fields.get("TLS_JA3")),
                ("JA3S", fields.get("TLS_JA3S")),
                ("IP de destino", dest_ip),
            ),
            recommended_actions=[
                "Revisar reputacao de dominio, URL e fingerprint TLS associados ao fluxo.",
                "Correlacionar o mesmo host, JA3 ou SNI em proxy, firewall e DNS.",
                "Validar se o fluxo representa entrega inicial, beaconing ou trafego de navegacao esperado.",
            ],
            mitre_techniques=[
                {"id": "T1071.001", "reason": "Canal HTTP/HTTPS ou TLS relevante observado na telemetria."},
            ],
        )

    if _clean_text(dns_query) and (dest_port == "53" or _contains_any(raw_text.lower(), ("dns", "resolver", "query"))) and (
        (bytes_out is not None and bytes_in is not None and bytes_out >= max(bytes_in * 3, 2048))
        or len(_clean_text(dns_query)) >= 40
    ):
        _append_context(
            contexts,
            seen,
            context_id="dns_anomalous_channel",
            family="dns_http_tls",
            title="Sinal de uso anomalo de DNS",
            summary="O evento apresenta DNS com volume de saida ou comprimento de consulta acima do habitual.",
            confidence=0.67,
            severity="medium",
            rationale="Consultas DNS muito extensas ou acompanhadas de forte assimetria de bytes podem indicar tunelamento, beaconing ou resolucao anomala.",
            evidence=_build_evidence(
                ("DNS", dns_query),
                ("Porta de destino", dest_port),
                ("Bytes entrada", bytes_in),
                ("Bytes saida", bytes_out),
            ),
            recommended_actions=[
                "Verificar volume e periodicidade das consultas DNS para o mesmo host ou dominio.",
                "Inspecionar se a consulta DNS esta ligada a tunelamento, DGA ou resolucao de infraestrutura suspeita.",
            ],
            mitre_techniques=[
                {"id": "T1071.004", "reason": "Uso anomalo de DNS sugerido pela telemetria observada."},
            ],
        )

    process_text = f"{process_name} {command_line}".lower()
    selected_lolbin: dict[str, str] | None = None
    if process_text:
        for markers, technique in _LOLBIN_TECHNIQUES:
            if any(marker in process_text for marker in markers):
                selected_lolbin = technique
                break
    if selected_lolbin:
        _append_context(
            contexts,
            seen,
            context_id="lolbin_execution",
            family="process_endpoint",
            title="Execucao por LOLBin ou interpretador",
            summary="O payload envolve binario de sistema ou interpretador frequentemente usado em execucao, evasao ou entrega de payload.",
            confidence=0.79,
            severity="high",
            rationale="Binarios nativos como PowerShell, mshta, regsvr32 ou rundll32 sao frequentemente reutilizados por atacantes para reduzir deteccao.",
            evidence=_build_evidence(
                ("Processo", process_name),
                ("Linha de comando", command_line),
                ("Modulo", fields.get("Modulo")),
            ),
            recommended_actions=[
                "Correlacionar arvore de processo, filho/pai e carregamento de modulo para o host afetado.",
                "Validar se a linha de comando e esperada para o ativo, usuario e janela operacional.",
                "Preservar artefatos de execucao e revisar telemetria EDR complementar.",
            ],
            mitre_techniques=[selected_lolbin],
        )

    persistence_mitre: list[dict[str, str]] = []
    if "currentversion\\run" in registry_path.lower():
        persistence_mitre.append({"id": "T1547.001", "reason": "Chave Run de registro observada no payload."})
    if service_name:
        persistence_mitre.append({"id": "T1543.003", "reason": "Servico observado como possivel mecanismo de persistencia."})
    if any(token in command_line.lower() for token in ("schtasks", "at.exe")):
        persistence_mitre.append({"id": "T1053.005", "reason": "Tarefa agendada observada no contexto da execucao."})
    if persistence_mitre:
        _append_context(
            contexts,
            seen,
            context_id="persistence_registry_service",
            family="process_endpoint",
            title="Indicativo de persistencia no endpoint",
            summary="Ha sinais de mecanismo de persistencia envolvendo registro, servico ou tarefa agendada.",
            confidence=0.82,
            severity="high",
            rationale="Persistencia via Run key, servico ou tarefa agendada costuma alterar a superficie de recorrencia do comprometimento.",
            evidence=_build_evidence(
                ("Registro", registry_path),
                ("Servico", service_name),
                ("Linha de comando", command_line),
            ),
            recommended_actions=[
                "Validar alteracoes de persistencia no host e comparar com baseline administrativo.",
                "Revisar criacao recente de servicos, tarefas e chaves de inicializacao automatica.",
                "Considerar erradicacao do mecanismo de persistencia antes de recolocar o ativo em producao.",
            ],
            mitre_techniques=persistence_mitre,
        )

    external_target = _is_external_ip(dest_ip) or any(
        _clean_text(value) for value in (url, dns_query, http_host, tls_sni)
    )
    if bytes_out is not None and bytes_in is not None and bytes_out >= max(bytes_in * 3, 2048) and external_target:
        _append_context(
            contexts,
            seen,
            context_id="outbound_exfiltration_signal",
            family="network_flow_nat",
            title="Assimetria de trafego de saida",
            summary="O volume de saida supera significativamente o de entrada em direcao a destino externo ou identificador de rede relevante.",
            confidence=0.74,
            severity="high",
            rationale="Assimetria relevante de bytes em saida pode sinalizar exfiltracao, upload anomalo ou resposta excessiva a canal externo.",
            evidence=_build_evidence(
                ("Bytes entrada", bytes_in),
                ("Bytes saida", bytes_out),
                ("IP de destino", dest_ip),
                ("URL", url),
                ("DNS", dns_query),
            ),
            recommended_actions=[
                "Confirmar se o volume de saida e esperado para o ativo e para a aplicacao envolvida.",
                "Correlacionar uploads, transferencias e chamadas HTTP/DNS do mesmo host no periodo.",
                "Avaliar necessidade de bloqueio temporario do destino enquanto o fluxo e investigado.",
            ],
            mitre_techniques=[
                {"id": "T1041", "reason": "Forte assimetria de trafego de saida para destino externo observada."},
            ],
        )

    if _clean_text(cloud_account) or _clean_text(cloud_resource) or _clean_text(cloud_role):
        _append_context(
            contexts,
            seen,
            context_id="cloud_identity_scope",
            family="cloud_identity",
            title="Evento com contexto de identidade ou recurso cloud",
            summary="A telemetria envolve conta, papel ou recurso cloud, o que amplia o escopo potencial do incidente.",
            confidence=0.66 if (_is_external_ip(source_ip) or auth_lower) else 0.58,
            severity="medium",
            rationale="Eventos cloud com conta, role ou resourceId pedem validacao de permissao, escopo e impacto em workload ou tenant.",
            evidence=_build_evidence(
                ("Cloud conta", cloud_account),
                ("Cloud recurso", cloud_resource),
                ("Cloud papel", cloud_role),
                ("Cloud tenant", fields.get("Cloud_Tenant_ID")),
                ("Cloud regiao", fields.get("Cloud_Regiao")),
                ("IP de origem", source_ip),
            ),
            recommended_actions=[
                "Revisar trilha de auditoria do recurso e da identidade cloud no mesmo periodo.",
                "Confirmar se o role e o recurso sao esperados para o usuario, origem e horario observados.",
                "Avaliar necessidade de conter credenciais, tokens ou chaves associados ao recurso cloud.",
            ],
            mitre_techniques=[
                {"id": "T1078", "reason": "Contexto de identidade cloud exige validacao de uso de conta valida ou abuso de permissao."},
            ] if (_is_external_ip(source_ip) or auth_lower) else [],
        )

    if _clean_text(kubernetes_pod) or _clean_text(container_id) or _clean_text(container_image):
        _append_context(
            contexts,
            seen,
            context_id="kubernetes_workload_scope",
            family="kubernetes_container",
            title="Evento impacta workload Kubernetes ou container",
            summary="A evidência está associada a pod, namespace ou container, exigindo análise de escopo no workload.",
            confidence=0.62,
            severity="medium",
            rationale="Telemetria de pod/container muda o contexto de investigação para workload, imagem, service account e cluster.",
            evidence=_build_evidence(
                ("Kubernetes pod", kubernetes_pod),
                ("Kubernetes namespace", kubernetes_namespace),
                ("Container ID", container_id),
                ("Container imagem", container_image),
                ("Kubernetes cluster", fields.get("Kubernetes_Cluster")),
            ),
            recommended_actions=[
                "Correlacionar o evento com image provenance, service account e namespace do workload.",
                "Revisar outros pods do mesmo deployment ou node em busca de comportamento semelhante.",
                "Avaliar necessidade de isolar o workload ou rotacionar credenciais montadas no pod.",
            ],
        )

    if _clean_text(nat_src) or _clean_text(nat_dst):
        _append_context(
            contexts,
            seen,
            context_id="nat_network_path",
            family="network_flow_nat",
            title="Caminho NAT identificado",
            summary="A telemetria inclui traducao NAT, o que pode afetar a atribuicao correta de origem e destino.",
            confidence=0.55,
            severity="low",
            rationale="Presenca de NAT e importante para nao atribuir incorretamente a comunicacao a um host ou rede errados.",
            evidence=_build_evidence(
                ("NAT origem", nat_src),
                ("NAT destino", nat_dst),
                ("Interface", fields.get("Interface_Rede")),
                ("Zona", fields.get("Zona_Rede")),
            ),
            recommended_actions=[
                "Correlacionar o fluxo com logs de firewall ou balanceador para reconstruir origem e destino reais.",
            ],
        )

    contexts.sort(key=lambda item: (item.get("confidence", 0.0), item.get("severity") == "high"), reverse=True)
    return contexts[:10]


def enrich_analysis_with_contexts(
    analysis: dict[str, Any],
    fields: dict[str, Any],
    ti_results: dict[str, str] | None = None,
    raw_text: str = "",
) -> dict[str, Any]:
    enriched = dict(analysis or {})
    enriched["contextos_investigativos"] = build_security_contexts(
        fields=fields,
        ti_results=ti_results,
        raw_text=raw_text,
    )
    return enriched
