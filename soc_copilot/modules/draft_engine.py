"""
draft_engine.py
Geração de saída controlada via templates para cada classificação.
Regras aplicadas:
  - Sem markdown
  - Acentuação e cedilha obrigatórias
  - Bloco "Análise do IP:" só aparece quando há conteúdo relevante
  - Recomendação sempre anonimizada
  - Estrutura aderente ao SOP e ao inventário do MVP
  - Exceção Icatu: repasse técnico em casos não-TP
"""
from __future__ import annotations

import re

from soc_copilot.modules.rule_loader import RulePack

CLASSIFICACOES = {
    "TP": "True Positive",
    "BTP": "Benign True Positive",
    "FP": "False Positive",
    "TN": "True Negative",
    "LTF": "Log Transmission Failure",
}

_MARKDOWN_PATTERNS = ("```", "**", "__", "# ")


def _field(value: object) -> str:
    text = str(value or "").strip()
    return text if text and text.lower() not in {"none", "null", "n/a"} else "N/A"


def _has_value(value: object) -> bool:
    return _field(value) != "N/A"


def _clean_inline(text: object) -> str:
    cleaned = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    for marker in _MARKDOWN_PATTERNS:
        cleaned = cleaned.replace(marker, "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _ensure_sentence(text: object, fallback: str = "") -> str:
    cleaned = _clean_inline(text)
    if not cleaned:
        cleaned = fallback
    if not cleaned:
        return ""
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def _finalize_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    for marker in _MARKDOWN_PATTERNS:
        cleaned = cleaned.replace(marker, "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = "\n".join(line.rstrip() for line in cleaned.splitlines())
    return cleaned.strip()


def _safe_join(parts: list[str], sep: str = " ") -> str:
    return sep.join(part for part in parts if part)


def _analysis_dict(analysis: dict | None) -> dict:
    return analysis if isinstance(analysis, dict) else {}


def _top_hypothesis(analysis: dict) -> dict:
    hipoteses = analysis.get("hipoteses", [])
    return hipoteses[0] if isinstance(hipoteses, list) and hipoteses else {}


def _build_title(fields: dict, analysis: dict, fallback: str) -> str:
    assunto = _field(fields.get("Assunto"))
    if assunto != "N/A":
        return assunto

    factual = analysis.get("resumo_factual", {})
    title = _clean_inline(factual.get("o_que", ""))
    if title:
        return title[0].upper() + title[1:]

    return fallback


def _build_context_sentence(fields: dict, lead: str) -> str:
    horario = _field(fields.get("Horario"))
    usuario = _field(fields.get("Usuario"))
    ip = _field(fields.get("IP_Origem"))
    destino = _field(fields.get("Destino"))

    detalhes: list[str] = []
    if horario != "N/A":
        detalhes.append(f"às {horario}")
    if usuario != "N/A":
        detalhes.append(f"envolvendo o usuário {usuario}")
    if ip != "N/A":
        detalhes.append(f"com origem em {ip}")
    if destino != "N/A":
        detalhes.append(f"e destino em {destino}")

    if detalhes:
        return _ensure_sentence(f"{lead} O evento foi observado " + ", ".join(detalhes))
    return _ensure_sentence(lead)


def _build_detail_lines(fields: dict) -> list[str]:
    lines = []
    usuario = _field(fields.get("Usuario"))
    ip = _field(fields.get("IP_Origem"))
    destino = _field(fields.get("Destino"))
    caminho = _field(fields.get("Caminho"))
    log_source = _field(fields.get("LogSource"))

    # Campos de identidade sempre exibidos — "N/A" é informação relevante para o analista
    lines.append(f"Usuário: {usuario}")
    lines.append(f"IP de Origem: {ip}")
    # Campos contextuais: omitidos quando ausentes para não gerar ruído no draft
    if destino != "N/A":
        lines.append(f"Destino: {destino}")
    if caminho != "N/A":
        lines.append(f"Diretório/Caminho: {caminho}")
    lines.append(f"Log Source: {log_source}")
    return lines


def _non_warning_ti(ti_results: dict[str, str]) -> list[tuple[str, str]]:
    valid: list[tuple[str, str]] = []
    for ioc, resultado in (ti_results or {}).items():
        summary = _clean_inline(resultado)
        if not summary:
            continue
        if "[AVISO]" in summary or "[ERRO]" in summary:
            continue
        valid.append((ioc, summary))
    return valid


def _build_ip_analysis(ti_results: dict[str, str]) -> str:
    valid = _non_warning_ti(ti_results)
    if not valid:
        return ""

    # Escolhe o label do bloco conforme o tipo de artefato predominante
    iocs_nomes = [ioc for ioc, _ in valid]
    tem_ip = any(
        all(part.isdigit() for part in ioc.replace("[.]", ".").split(".") if part)
        for ioc in iocs_nomes
    )
    label = "Análise do IP:" if tem_ip else "Análise de Indicadores:"

    lines = [label]
    if len(valid) == 1:
        ioc, resultado = valid[0]
        lines.append(
            _ensure_sentence(
                f"Foram consultadas bases de Threat Intelligence para o artefato {ioc}, com o seguinte retorno: {resultado}"
            )
        )
    else:
        lines.append(
            "Foram consultadas bases de Threat Intelligence para os artefatos externos identificados, com os seguintes retornos:"
        )
        for ioc, resultado in valid:
            lines.append(f"{ioc}: {resultado}")
    return "\n".join(lines)


def _rationale_for(classificacao: str, analysis: dict) -> str:
    """
    Retorna o racional da hipótese que corresponde à classificação escolhida.
    Evita que a sugestão automática (ex: TP) vaze para um draft de outra classificação (ex: LTF).
    """
    label_esperado = CLASSIFICACOES.get(classificacao.upper(), "")
    for h in analysis.get("hipoteses", []):
        if h.get("tipo", "") == label_esperado:
            return _clean_inline(h.get("justificativa", h.get("racional", "")))
    # Nenhuma hipótese bate com a classificação escolhida — usa o racional geral só se compatível
    cls_info = analysis.get("classificacao_sugerida", {})
    sugerida = cls_info.get("tipo", "")
    if sugerida == label_esperado:
        return _clean_inline(cls_info.get("racional", ""))
    return ""


def _build_technical_analysis(classificacao: str, analysis: dict, ti_results: dict[str, str]) -> str:
    rationale = _rationale_for(classificacao, analysis)

    if classificacao == "TP":
        fallback = "As evidências analisadas sustentam a classificação do caso como potencial incidente de segurança e demandam tratativa imediata."
    elif classificacao == "BTP":
        fallback = "A atividade observada é real e foi corretamente detectada, porém o contexto analisado indica comportamento legítimo e esperado."
    elif classificacao == "LTF":
        fallback = "Os elementos disponíveis apontam limitação operacional na coleta, transmissão ou integridade dos logs necessários para análise."
    else:
        fallback = "As evidências analisadas não sustentam a caracterização de incidente de segurança no contexto observado."

    paragraph = _ensure_sentence(rationale, fallback)
    if _non_warning_ti(ti_results):
        paragraph = _safe_join(
            [
                paragraph,
                "A consulta de Threat Intelligence agregou contexto aos artefatos externos observados e foi considerada na conclusão técnica.",
            ]
        )
        paragraph = _ensure_sentence(paragraph)

    lacunas = analysis.get("lacunas", [])
    if isinstance(lacunas, list) and lacunas:
        itens_limpos = [_clean_inline(item) for item in lacunas if _clean_inline(item)]
        MAX_LACUNAS = 3
        if len(itens_limpos) > MAX_LACUNAS:
            sufixo = f" (e outras {len(itens_limpos) - MAX_LACUNAS} limitação/ões não listadas)"
            itens_limpos = itens_limpos[:MAX_LACUNAS]
        else:
            sufixo = ""
        paragraph = _safe_join(
            [
                paragraph,
                _ensure_sentence(
                    f"Persistem limitações de evidência a serem consideradas: {'; '.join(itens_limpos)}{sufixo}",
                    "",
                ),
            ]
        )
    return paragraph


def _build_reference_and_mitre(analysis: dict) -> tuple[str, str]:
    mitre = analysis.get("mitre_candidato", {})
    tecnica = _clean_inline(mitre.get("tecnica", ""))
    justificativa = _ensure_sentence(mitre.get("justificativa", ""))

    if tecnica:
        if re.fullmatch(r"T\d{4}(?:\.\d{3})?", tecnica):
            if "." in tecnica:
                parent, child = tecnica.split(".", 1)
                link = f"https://attack.mitre.org/techniques/{parent}/{child}/"
            else:
                link = f"https://attack.mitre.org/techniques/{tecnica}/"
        else:
            link = tecnica

        referencia = justificativa or _ensure_sentence(
            f"A atividade observada apresenta aderência técnica ao comportamento descrito em {tecnica}"
        )
        return referencia, link

    return (
        "O mapeamento MITRE deve ser validado conforme o contexto técnico específico do evento analisado.",
        "Mapeamento MITRE pendente de validação técnica.",
    )


def _tp_recommendation() -> str:
    return (
        "Recomendamos validar imediatamente a legitimidade da atividade observada, revisar os logs correlatos do período, "
        "conter o ativo impactado caso haja indícios adicionais de comprometimento e aplicar as ações de remediação "
        "cabíveis conforme o procedimento interno do ambiente."
    )


def _repasse_recommendation() -> str:
    return (
        "A validação da ocorrência e a continuidade da tratativa cabem ao time de Segurança do cliente, "
        "ficando o SOC iT.eam à disposição para suporte técnico complementar, se necessário."
    )


def _build_tp(fields: dict, ti_results: dict[str, str], analysis: dict) -> str:
    title = _build_title(fields, analysis, "Identificada atividade suspeita com potencial impacto à segurança")
    factual = analysis.get("resumo_factual", {})
    lead = _ensure_sentence(
        factual.get("o_que", ""),
        "Foi identificada atividade com relevância para segurança a partir da telemetria analisada.",
    )
    narrativa = _build_context_sentence(fields, lead)
    referencia, mitre_link = _build_reference_and_mitre(analysis)

    sections = [
        "Prezados,",
        "",
        title,
        "",
        narrativa,
        "",
        "\n".join(_build_detail_lines(fields)),
    ]

    bloco_ip = _build_ip_analysis(ti_results)
    if bloco_ip:
        sections.extend(["", bloco_ip])

    sections.extend(
        [
            "",
            "Análise Técnica:",
            _build_technical_analysis("TP", analysis, ti_results),
            "",
            "Em anexo o Payload.",
            "",
            "Referência:",
            referencia,
            "",
            "Referência MITRE:",
            mitre_link,
            "",
            "Recomendação:",
            _tp_recommendation(),
        ]
    )
    return _finalize_text("\n".join(sections))


def _build_btp(fields: dict, analysis: dict) -> str:
    factual = analysis.get("resumo_factual", {})
    summary = _ensure_sentence(
        factual.get("o_que", ""),
        "A atividade observada foi corretamente identificada pela regra de detecção e confirmada como comportamento benigno.",
    )
    rationale = _build_technical_analysis("BTP", analysis, {})
    action = "Encerrar o caso como Benign True Positive, sem indicação de impacto adverso ao ambiente."

    sections = [
        "Classificação Final: Benign True Positive",
        "",
        "Resumo Técnico:",
        _build_context_sentence(fields, summary),
        "",
        "Justificativa da benignidade:",
        rationale,
        "",
        "Ação de encerramento:",
        action,
    ]
    return _finalize_text("\n".join(sections))


def _build_fp_tn_ltf(classificacao: str, fields: dict, analysis: dict) -> str:
    label = CLASSIFICACOES.get(classificacao, classificacao)
    justificativa = _build_technical_analysis(classificacao, analysis, {})

    if classificacao == "FP":
        action = "Registrar o caso como False Positive e avaliar necessidade de ajuste na regra caso a recorrência persista."
    elif classificacao == "TN":
        action = "Registrar o evento como atividade não maliciosa e manter monitoramento conforme o fluxo operacional."
    elif classificacao == "LTF":
        action = "Acionar o responsável pela fonte de logs para validar coleta, transmissão e integridade dos eventos necessários à análise."
    else:
        action = "Registrar a conclusão técnica conforme o procedimento operacional vigente."

    sections = [
        f"Classificação Final: {label}",
        "",
        "Justificativa:",
        _build_context_sentence(fields, justificativa),
        "",
        "Ação recomendada:",
        action,
    ]
    return _finalize_text("\n".join(sections))


def _build_icatu_repasse(classificacao: str, fields: dict, ti_results: dict[str, str], analysis: dict) -> str:
    label = CLASSIFICACOES.get(classificacao, classificacao)
    title = _build_title(fields, analysis, f"Encaminhamento técnico de evento classificado como {label}")
    factual = analysis.get("resumo_factual", {})
    lead = _ensure_sentence(
        factual.get("o_que", ""),
        f"O SOC iT.eam concluiu a análise técnica do evento com classificação {label}.",
    )

    sections = [
        "Prezados,",
        "",
        title,
        "",
        _build_context_sentence(fields, lead),
        "",
        "\n".join(_build_detail_lines(fields)),
    ]

    bloco_ip = _build_ip_analysis(ti_results)
    if bloco_ip:
        sections.extend(["", bloco_ip])

    sections.extend(
        [
            "",
            "Análise Técnica:",
            _build_technical_analysis(classificacao, analysis, ti_results),
            "",
            "Encaminhamento:",
            _repasse_recommendation(),
        ]
    )
    return _finalize_text("\n".join(sections))


def generate(
    classificacao: str,
    fields: dict,
    ti_results: dict[str, str],
    pack: RulePack,
    analysis: dict | None = None,
) -> tuple[str, str]:
    """
    Gera o draft final conforme a classificação.
    Retorna (draft_text, template_usado).
    """
    cls = classificacao.upper()
    analysis = _analysis_dict(analysis)

    if pack.is_icatu and cls != "TP":
        return _build_icatu_repasse(cls, fields, ti_results, analysis), f"icatu_repasse_{cls.lower()}"

    if cls == "TP":
        template = pack.modelo_nome or "sop_tp_padrao"
        return _build_tp(fields, ti_results, analysis), template

    if cls == "BTP":
        return _build_btp(fields, analysis), "sop_btp"

    if cls in {"FP", "TN", "LTF"}:
        return _build_fp_tn_ltf(cls, fields, analysis), f"sop_{cls.lower()}"

    draft = _finalize_text(
        "\n".join(
            [
                f"Classificação Final: {classificacao}",
                "",
                "Justificativa:",
                "A classificação informada não possui template específico no Draft Engine e deve ser revisada manualmente.",
            ]
        )
    )
    return draft, "nao_mapeado"
