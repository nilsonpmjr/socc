from __future__ import annotations

from typing import Any


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.upper() in {"", "N/A", "NONE", "NULL"} else text


def _push_fact(
    target: list[dict[str, str]],
    category: str,
    label: str,
    value: Any,
    source: str,
) -> None:
    cleaned = _clean_text(value)
    if not cleaned:
        return
    target.append(
        {
            "category": category,
            "label": label,
            "value": cleaned,
            "source": source,
        }
    )


def _push_inference(
    target: list[dict[str, Any]],
    inference_type: str,
    statement: str,
    rationale: str = "",
    confidence: Any = None,
) -> None:
    cleaned_statement = _clean_text(statement)
    if not cleaned_statement:
        return
    item: dict[str, Any] = {
        "type": inference_type,
        "statement": cleaned_statement,
        "rationale": _clean_text(rationale),
    }
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        item["confidence"] = max(0.0, min(1.0, float(confidence)))
    target.append(item)


def build_analysis_trace(
    fields: dict[str, Any],
    analysis: dict[str, Any],
    ti_results: dict[str, str] | None = None,
) -> dict[str, Any]:
    ti_results = ti_results or {}
    observed_facts: list[dict[str, str]] = []
    inferences: list[dict[str, Any]] = []
    limitations: list[str] = []

    for label, key in (
        ("Horario", "Horario"),
        ("Usuario", "Usuario"),
        ("IP de Origem", "IP_Origem"),
        ("IP de Destino", "IP_Destino"),
        ("Destino", "Destino"),
        ("Hostname", "Hostname"),
        ("Servidor", "Servidor"),
        ("Caminho", "Caminho"),
        ("Arquivo", "Arquivo"),
        ("Hash Observado", "Hash_Observado"),
        ("Log Source", "LogSource"),
        ("Assunto", "Assunto"),
        ("Porta de Origem", "Porta_Origem"),
        ("Porta de Destino", "Porta_Destino"),
        ("Email Remetente", "Email_Remetente"),
        ("Email Destinatario", "Email_Destinatario"),
        ("Email Reply-To", "Email_ReplyTo"),
        ("Email Assunto", "Email_Assunto"),
        ("Resultado de Autenticacao", "Resultado_Autenticacao"),
        ("MFA", "MFA_Status"),
        ("Sessao", "Sessao_ID"),
        ("Tipo de Logon", "Tipo_Logon"),
        ("DNS Consulta", "DNS_Consulta"),
        ("HTTP Host", "HTTP_Host"),
        ("URL Completa", "URL_Completa"),
        ("User Agent", "User_Agent"),
        ("TLS SNI", "TLS_SNI"),
        ("TLS JA3", "TLS_JA3"),
        ("TLS JA3S", "TLS_JA3S"),
        ("Certificado", "Certificado_Assunto"),
        ("Processo", "Processo"),
        ("Processo Pai", "Processo_Pai"),
        ("Linha de Comando", "Linha_De_Comando"),
        ("Registro", "Registro"),
        ("Servico", "Servico"),
        ("Modulo", "Modulo"),
        ("Cloud Conta", "Cloud_Conta_ID"),
        ("Cloud Regiao", "Cloud_Regiao"),
        ("Cloud Recurso", "Cloud_Recurso"),
        ("Cloud Papel", "Cloud_Papel"),
        ("Cloud Tenant", "Cloud_Tenant_ID"),
        ("Cloud Projeto", "Cloud_Projeto_ID"),
        ("Bytes Entrada", "Bytes_Entrada"),
        ("Bytes Saida", "Bytes_Saida"),
        ("Pacotes Entrada", "Pacotes_Entrada"),
        ("Pacotes Saida", "Pacotes_Saida"),
        ("Direcao Rede", "Direcao_Rede"),
        ("NAT IP Origem", "NAT_IP_Origem"),
        ("NAT IP Destino", "NAT_IP_Destino"),
        ("Sessao Rede", "Sessao_Rede_ID"),
        ("Zona Rede", "Zona_Rede"),
        ("Interface Rede", "Interface_Rede"),
        ("Kubernetes Pod", "Kubernetes_Pod"),
        ("Kubernetes Namespace", "Kubernetes_Namespace"),
        ("Container ID", "Container_ID"),
        ("Container Imagem", "Container_Imagem"),
        ("Kubernetes Node", "Kubernetes_Node"),
        ("Kubernetes Cluster", "Kubernetes_Cluster"),
        ("Kubernetes ServiceAccount", "Kubernetes_ServiceAccount"),
        ("Kubernetes Workload", "Kubernetes_Workload"),
    ):
        _push_fact(observed_facts, "field", label, fields.get(key), "parser_engine")

    iocs = fields.get("IOCs") or {}
    for label, key in (
        ("IP externo", "ips_externos"),
        ("IP interno", "ips_internos"),
        ("URL", "urls"),
        ("Dominio", "dominios"),
        ("Hash", "hashes"),
    ):
        for value in iocs.get(key, []) or []:
            _push_fact(observed_facts, "ioc", label, value, "parser_engine")

    for ioc, result in ti_results.items():
        _push_fact(observed_facts, "threat_intel", ioc, result, "ti_adapter")

    suggested = analysis.get("classificacao_sugerida") or {}
    _push_inference(
        inferences,
        "classification",
        f"Classificacao sugerida: {_clean_text(suggested.get('tipo')) or 'indefinida'}",
        rationale=_clean_text(suggested.get("racional")) or _clean_text(suggested.get("justificativa")),
        confidence=suggested.get("confianca"),
    )

    for hypothesis in (analysis.get("hipoteses") or [])[:3]:
        _push_inference(
            inferences,
            "hypothesis",
            f"Hipotese: {_clean_text(hypothesis.get('tipo')) or 'sem rotulo'}",
            rationale=_clean_text(hypothesis.get("justificativa")) or _clean_text(hypothesis.get("racional")),
            confidence=hypothesis.get("confianca"),
        )

    for context in (analysis.get("contextos_investigativos") or [])[:5]:
        _push_inference(
            inferences,
            "security_context",
            f"Contexto investigativo: {_clean_text(context.get('title')) or 'Contexto sem titulo'}",
            rationale=_clean_text(context.get("summary")) or _clean_text(context.get("rationale")),
            confidence=context.get("confidence"),
        )

    mitre = analysis.get("mitre_candidato") or {}
    technique = _clean_text(mitre.get("tecnica"))
    if technique:
        _push_inference(
            inferences,
            "mitre",
            f"TTP candidata: {technique}",
            rationale=_clean_text(mitre.get("justificativa")),
        )

    for item in (analysis.get("lacunas") or []) + (analysis.get("alertas_de_qualidade") or []):
        cleaned = _clean_text(item)
        if cleaned and cleaned not in limitations:
            limitations.append(cleaned)

    return {
        "observed_facts": observed_facts,
        "inferences": inferences,
        "limitations": limitations,
    }
