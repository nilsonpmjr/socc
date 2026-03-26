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


# ---------------------------------------------------------------------------
# Geração de análise textual contextual — converte dados reais em prosa
# ---------------------------------------------------------------------------

_ATTACK_PATTERNS: list[tuple[str, str]] = [
    (r"log4j|log4shell|jndi|cve-2021-44228",
     "A assinatura detectada refere-se a uma tentativa de exploração da vulnerabilidade Log4Shell "
     "(CVE-2021-44228), que permite execução remota de código via JNDI injection no componente "
     "Log4j do Apache. A técnica é amplamente explorada por agentes de ameaça para obter acesso "
     "inicial em servidores que processam logs com dados controlados pelo atacante."),
    (r"\.dos\b|denial.of.service|thread.context.dos|http.flood|syn.flood|udp.flood",
     "A assinatura indica tentativa de ataque de negação de serviço (DoS/DDoS), cujo objetivo é "
     "tornar um serviço ou recurso indisponível ao saturar sua capacidade de processamento ou "
     "banda disponível."),
    (r"sql.inject|sqli\b|\bsqli\b|sql injection",
     "A assinatura indica tentativa de injeção SQL, técnica onde o atacante insere comandos "
     "maliciosos em campos de entrada para manipular consultas ao banco de dados, podendo resultar "
     "em extração, modificação ou exclusão de dados sensíveis."),
    (r"path.travers|directory.travers|\blfi\b|\brfi\b|file.inclusion",
     "A assinatura indica tentativa de path traversal ou inclusão de arquivo remoto/local, "
     "onde o atacante tenta acessar arquivos fora do diretório raiz da aplicação web ou "
     "incluir arquivos maliciosos no contexto da aplicação."),
    (r"xss|cross.site.script",
     "A assinatura indica tentativa de Cross-Site Scripting (XSS), onde o atacante injeta "
     "scripts maliciosos em páginas web com o objetivo de comprometer sessões de usuários "
     "legítimos ou redirecionar para conteúdo malicioso."),
    (r"shellshock|bash.remote.code",
     "A assinatura indica tentativa de exploração da vulnerabilidade Shellshock (CVE-2014-6271), "
     "que permite execução arbitrária de código via variáveis de ambiente do interpretador Bash."),
    (r"brute.force|bruteforce|password.spray|login.attempt|account.lockout",
     "A assinatura indica atividade de força bruta ou pulverização de senhas, técnica onde "
     "o atacante tenta múltiplas combinações de credenciais para obter acesso não autorizado "
     "a contas ou sistemas."),
    (r"ptr.scan|dns.ptr|reverse.dns.scan",
     "A assinatura indica varredura de registros DNS reverso (PTR Scan), técnica de "
     "reconhecimento usada para descobrir nomes de hosts associados a endereços IP, "
     "permitindo ao atacante mapear a topologia e a infraestrutura interna da rede."),
    (r"port.scan|portscan|tcp.scan|udp.scan|host.discovery|ping.sweep",
     "A assinatura indica varredura de portas ou descoberta de hosts, atividade de "
     "reconhecimento usada para identificar serviços ativos, versões de software e "
     "possíveis vetores de ataque em sistemas da rede."),
    (r"ransomware|file.encrypt|\.locked|\.encrypted|ransom",
     "A assinatura indica atividade associada a ransomware, incluindo possível criptografia "
     "de arquivos ou comunicação com infraestrutura de comando e controle de campanhas "
     "de extorsão digital."),
    (r"mimikatz|credential.dump|lsass|ntds\.dit",
     "A assinatura indica tentativa de despejo de credenciais do sistema operacional, "
     "técnica usada para extrair senhas, hashes e tokens de autenticação da memória "
     "ou de arquivos críticos do Windows."),
    (r"lateral.movement|psexec|pass.the.hash|wmi.remote|smb.exec",
     "A assinatura indica atividade de movimentação lateral, técnica usada por atacantes "
     "para se propagar de um sistema comprometido para outros ativos da rede interna, "
     "expandindo o escopo do comprometimento."),
    (r"c2|command.and.control|beacon|beaconing|callback",
     "A assinatura indica comunicação com infraestrutura de comando e controle (C2), "
     "padrão típico de malware que se reporta periodicamente a um servidor controlado "
     "pelo atacante para receber instruções."),
    (r"exfil|data.theft|large.upload|unusual.upload",
     "A assinatura indica atividade suspeita de exfiltração de dados, onde volumes "
     "incomuns de informação são transferidos para destinos externos não autorizados."),
]

_KNOWN_SCANNER_TI: list[tuple[str, str]] = [
    ("tenable", "Tenable (Nessus)"),
    ("nessus", "Tenable Nessus"),
    ("qualys", "Qualys"),
    ("rapid7", "Rapid7"),
    ("openvas", "OpenVAS / Greenbone"),
    ("greenbone", "Greenbone Vulnerability Manager"),
    ("shodan", "Shodan"),
    ("censys", "Censys"),
    ("zmap", "ZMap"),
    ("masscan", "Masscan"),
]

_BLOCKED_ACTIONS_DESC = {
    "dropped":  "bloqueado e descartado",
    "drop":     "bloqueado e descartado",
    "blocked":  "bloqueado",
    "block":    "bloqueado",
    "reset":    "interrompido via TCP RST",
    "denied":   "negado",
    "deny":     "negado",
    "rejected": "rejeitado",
}

_ALLOWED_ACTIONS = {"allowed", "pass", "accept", "permit", "allow"}


def _describe_attack(assunto: str) -> str:
    """Converte nome de assinatura/regra em descrição analítica em português."""
    if not assunto or assunto == "N/A":
        return ""
    lower = assunto.lower()
    for pattern, desc in _ATTACK_PATTERNS:
        if re.search(pattern, lower):
            return desc
    return (
        f"A detecção foi gerada pela assinatura '{assunto}', "
        "indicando atividade potencialmente maliciosa identificada pelo controle de segurança."
    )


def _describe_source_from_ti(ip: str, ti_results: dict) -> str:
    """Caracteriza o IP de origem a partir dos resultados de TI."""
    if not ip or ip == "N/A" or not ti_results:
        return ""

    ti_text = " ".join(ti_results.values()).lower()

    # Scanner org
    for token, nome in _KNOWN_SCANNER_TI:
        if token in ti_text:
            return (
                f"O IP de origem {ip} foi identificado pelo Threat Intelligence como "
                f"pertencente à infraestrutura da {nome}, plataforma de gestão de "
                "vulnerabilidades amplamente utilizada em ambientes corporativos."
            )

    # VT score
    parts: list[str] = []
    vt_match = re.search(r"(\d+)/(\d+)\s*fornecedores", ti_text)
    if not vt_match:
        vt_match = re.search(r"pontuação[:\s]+(\d+)/(\d+)", ti_text)
    if vt_match:
        det = int(vt_match.group(1))
        total = int(vt_match.group(2))
        if det == 0:
            parts.append(f"não apresentou detecções maliciosas no VirusTotal ({det}/{total})")
        elif det <= 3:
            parts.append(f"apresentou {det} de {total} detecções no VirusTotal")
        else:
            parts.append(f"foi flagrado por {det} de {total} fornecedores no VirusTotal")

    # AbuseIPDB
    abuse_match = re.search(r"confiança[:\s]+(\d+)%", ti_text)
    if abuse_match:
        c = int(abuse_match.group(1))
        if c < 10:
            parts.append(f"índice de abuso AbuseIPDB de {c}% (baixo)")
        elif c >= 70:
            parts.append(f"índice de abuso AbuseIPDB de {c}% (alto)")
        else:
            parts.append(f"índice de abuso AbuseIPDB de {c}%")

    if parts:
        return f"O IP de origem {ip} " + " e ".join(parts) + "."
    return f"O IP de origem {ip} foi consultado nas bases de Threat Intelligence disponíveis."


def _describe_control_action(acao: str, destino: str) -> str:
    """Descreve o que o controle de segurança fez com o tráfego."""
    if not acao or acao in ("n/a", "N/A"):
        return ""
    acao_l = acao.strip().lower()
    dest_text = f" ao destino {destino}" if destino and destino != "N/A" else ""

    if acao_l in _BLOCKED_ACTIONS_DESC:
        desc = _BLOCKED_ACTIONS_DESC[acao_l]
        alvo = f" o destino {destino}" if destino and destino != "N/A" else " o host alvo"
        return (
            f"O tráfego foi {desc} pelo controle de segurança antes de atingir{alvo}, "
            "não havendo impacto direto no destino."
        )
    if acao_l in _ALLOWED_ACTIONS:
        return (
            f"O tráfego foi permitido pelo controle de segurança{dest_text}. "
            "É necessário avaliar o impacto nos sistemas de destino e verificar se houve execução bem-sucedida."
        )
    return f"Ação registrada pelo controle de segurança: '{acao}'{dest_text}."


def _scan_summary(fields: dict) -> str:
    resumo = _clean_inline(fields.get("Resumo_Scan", ""))
    return resumo if resumo and resumo.lower() not in {"n/a", "none", "null"} else ""


def _build_analytical_paragraph(
    classificacao: str,
    fields: dict,
    ti_results: dict,
    analysis: dict,
) -> str:
    """
    Gera parágrafo analítico contextual baseado nos dados reais do evento.
    Substitui o texto genérico por prosa derivada dos campos, TI e classificação.
    """
    assunto = _field(fields.get("Assunto"))
    acao = (fields.get("Acao") or "").strip()
    ip_origem = _field(fields.get("IP_Origem"))
    destino = _field(fields.get("Destino"))
    mitre = analysis.get("mitre_candidato", {})
    tecnica = _clean_inline(mitre.get("tecnica", ""))
    hipoteses = analysis.get("hipoteses", [])
    top_hip = hipoteses[0] if hipoteses else {}

    parts: list[str] = []

    # 1. Descrição do ataque / assinatura
    ataque = _describe_attack(assunto)
    if ataque:
        parts.append(ataque)

    # 2. Resumo consolidado quando o payload representa múltiplos eventos de scan.
    resumo_scan = _scan_summary(fields)
    if resumo_scan:
        parts.append(resumo_scan)

    # 3. Caracterização da fonte via TI
    fonte = _describe_source_from_ti(ip_origem, ti_results)
    if fonte:
        parts.append(fonte)

    # 4. Resposta do controle de segurança
    controle = _describe_control_action(acao, destino)
    if controle:
        parts.append(controle)

    # 5. Técnica MITRE em contexto — citar apenas o ID para não repetir a descrição do ataque
    if tecnica:
        parts.append(f"A atividade é mapeada em {tecnica} do framework MITRE ATT&CK.")

    # 6. Conclusão contextual por classificação
    # Para BTP: se a fonte já foi descrita via TI (scanner detectado), usar frase de fechamento simples
    # para não repetir o mesmo argumento duas vezes
    justificativa_hip = _clean_inline(top_hip.get("justificativa", ""))
    if classificacao == "BTP":
        if fonte:
            # Fonte já descrita — fechar com conclusão concisa
            parts.append(
                "A regra de detecção disparou corretamente ao identificar o padrão de ataque, "
                "porém o contexto da origem confirma tratar-se de atividade benigna."
            )
        elif justificativa_hip:
            parts.append(f"Contexto da classificação: {justificativa_hip}")
        else:
            parts.append("A atividade observada é real e foi corretamente detectada, porém o contexto indica comportamento legítimo e esperado.")
    elif classificacao == "TP":
        parts.append(
            "As evidências consolidadas sustentam a necessidade de investigação aprofundada e resposta imediata ao evento."
        )
    elif classificacao in ("FP", "TN"):
        parts.append(
            "A análise do contexto disponível indica que o evento não representa uma ameaça real ao ambiente monitorado."
        )
    elif classificacao == "LTF":
        parts.append(
            "A ausência ou inconsistência nos dados de log compromete a conclusão técnica definitiva — "
            "recomenda-se verificar a integridade e disponibilidade da fonte de logs antes de reanalisar o período."
        )

    # Fallback se nenhuma parte foi gerada
    if not parts:
        return _rationale_for(classificacao, analysis) or (
            "As evidências analisadas foram consideradas na conclusão técnica do caso."
        )

    return " ".join(parts)


def _build_technical_analysis(
    classificacao: str,
    analysis: dict,
    ti_results: dict[str, str],
    fields: dict | None = None,
) -> str:
    """Gera o bloco de Análise Técnica, priorizando texto analítico contextual."""
    if fields:
        paragraph = _build_analytical_paragraph(classificacao, fields, ti_results, analysis)
    else:
        # Fallback para o comportamento anterior quando fields não está disponível
        rationale = _rationale_for(classificacao, analysis)
        fallbacks = {
            "TP":  "As evidências analisadas sustentam a classificação do caso como potencial incidente de segurança e demandam tratativa imediata.",
            "BTP": "A atividade observada é real e foi corretamente detectada, porém o contexto analisado indica comportamento legítimo e esperado.",
            "LTF": "Os elementos disponíveis apontam limitação operacional na coleta, transmissão ou integridade dos logs necessários para análise.",
        }
        paragraph = _ensure_sentence(rationale, fallbacks.get(classificacao, "As evidências analisadas não sustentam a caracterização de incidente de segurança no contexto observado."))
        if _non_warning_ti(ti_results):
            paragraph = _ensure_sentence(_safe_join([paragraph, "A consulta de Threat Intelligence agregou contexto aos artefatos externos observados e foi considerada na conclusão técnica."]))

    lacunas = analysis.get("lacunas", [])
    if isinstance(lacunas, list) and lacunas:
        itens_limpos = [_clean_inline(item) for item in lacunas if _clean_inline(item)]
        MAX_LACUNAS = 3
        sufixo = f" (e outras {len(itens_limpos) - MAX_LACUNAS} limitação/ões não listadas)" if len(itens_limpos) > MAX_LACUNAS else ""
        itens_limpos = itens_limpos[:MAX_LACUNAS]
        paragraph = _safe_join([
            paragraph,
            _ensure_sentence(f"Persistem limitações de evidência a serem consideradas: {'; '.join(itens_limpos)}{sufixo}", ""),
        ])
    return paragraph


def _mitre_link(tecnica: str) -> str:
    if re.fullmatch(r"T\d{4}(?:\.\d{3})?", tecnica):
        if "." in tecnica:
            parent, child = tecnica.split(".", 1)
            return f"https://attack.mitre.org/techniques/{parent}/{child}/"
        return f"https://attack.mitre.org/techniques/{tecnica}/"
    return tecnica


def _build_reference_and_mitre(
    analysis: dict,
    pack: RulePack | None = None,
) -> tuple[str, str]:
    """
    Retorna (referencia_texto, link_mitre).
    Prioridade:
      1. Fragmentos do modelo real (mitre_descricao + mitre_referencia)
      2. Análise determinística (mitre_candidato)
      3. Fallback genérico
    """
    # 1. Fragmento do modelo real
    frag = getattr(pack, "modelo_fragmentos", None)
    if frag and frag.mitre_descricao:
        descricao = _clean_inline(frag.mitre_descricao)
        tecnica = frag.mitre_tecnica or ""
        link = _mitre_link(tecnica) if tecnica else (frag.mitre_referencia or "Mapeamento MITRE pendente de validação técnica.")
        return _ensure_sentence(descricao), link

    # 2. Análise determinística
    mitre = analysis.get("mitre_candidato", {})
    tecnica = _clean_inline(mitre.get("tecnica", ""))
    justificativa = _ensure_sentence(mitre.get("justificativa", ""))

    if tecnica:
        link = _mitre_link(tecnica)
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


def _build_proximos_passos_text(
    analysis: dict,
    fallback: str,
    pack: RulePack | None = None,
) -> str:
    """
    Monta o texto de recomendação.
    Prioridade:
      1. Recomendação do modelo real (anonimizada pelo model_parser)
      2. proximos_passos gerados pelo classification_helper
      3. fallback fixo
    """
    # 1. Recomendação do modelo real
    frag = getattr(pack, "modelo_fragmentos", None)
    if frag and frag.recomendacao:
        return _clean_inline(frag.recomendacao)

    # 2. proximos_passos da análise
    proximos = analysis.get("proximos_passos", [])
    itens = [_clean_inline(p) for p in (proximos or []) if _clean_inline(p)]
    if itens:
        return " ".join(
            item if item.endswith((".", "!", "?")) else item + "."
            for item in itens
        )

    return fallback


def _build_tp(fields: dict, ti_results: dict[str, str], analysis: dict, pack: RulePack | None = None) -> str:
    title = _build_title(fields, analysis, "Identificada atividade suspeita com potencial impacto à segurança")
    factual = analysis.get("resumo_factual", {})
    lead = _ensure_sentence(
        factual.get("o_que", ""),
        "Foi identificada atividade com relevância para segurança a partir da telemetria analisada.",
    )
    narrativa = _build_context_sentence(fields, lead)
    referencia, mitre_link = _build_reference_and_mitre(analysis, pack)

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
            _build_technical_analysis("TP", analysis, ti_results, fields),
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
            _build_proximos_passos_text(analysis, _tp_recommendation(), pack),
        ]
    )
    return _finalize_text("\n".join(sections))


def _build_btp(fields: dict, analysis: dict, pack: RulePack | None = None, ti_results: dict | None = None) -> str:
    factual = analysis.get("resumo_factual", {})
    summary = _ensure_sentence(
        factual.get("o_que", ""),
        "A atividade observada foi corretamente identificada pela regra de detecção e confirmada como comportamento benigno.",
    )
    rationale = _build_technical_analysis("BTP", analysis, ti_results or {}, fields)
    action = _build_proximos_passos_text(
        analysis,
        "Encerrar o caso como Benign True Positive, sem indicação de impacto adverso ao ambiente.",
        pack,
    )

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


def _build_fp_tn_ltf(classificacao: str, fields: dict, analysis: dict, pack: RulePack | None = None) -> str:
    label = CLASSIFICACOES.get(classificacao, classificacao)
    justificativa = _build_technical_analysis(classificacao, analysis, {}, fields)

    if classificacao == "FP":
        fallback_action = "Registrar o caso como False Positive e avaliar necessidade de ajuste na regra caso a recorrência persista."
    elif classificacao == "TN":
        fallback_action = "Registrar o evento como atividade não maliciosa e manter monitoramento conforme o fluxo operacional."
    elif classificacao == "LTF":
        fallback_action = "Acionar o responsável pela fonte de logs para validar coleta, transmissão e integridade dos eventos necessários à análise."
    else:
        fallback_action = "Registrar a conclusão técnica conforme o procedimento operacional vigente."

    action = _build_proximos_passos_text(analysis, fallback_action, pack)

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
            _build_technical_analysis(classificacao, analysis, ti_results, fields),
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
        return _build_tp(fields, ti_results, analysis, pack), template

    if cls == "BTP":
        return _build_btp(fields, analysis, pack, ti_results), "sop_btp"

    if cls in {"FP", "TN", "LTF"}:
        return _build_fp_tn_ltf(cls, fields, analysis, pack), f"sop_{cls.lower()}"

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
