"""
semi_llm_adapter.py
Contrato estrito da camada semi-LLM conforme PRD Seção 7.

Responsabilidades PERMITIDAS:
  - resumir tecnicamente o comportamento observado
  - organizar o quê / onde / quem / quando / por quê
  - sugerir hipóteses ranqueadas
  - apontar lacunas de evidência
  - sugerir classificação candidata com justificativa
  - sugerir técnica MITRE candidata
  - sugerir o modelo mais aderente
  - validar qualidade textual e aderência ao SOP

Responsabilidades PROIBIDAS:
  - decidir sozinha a classificação final
  - gerar texto final solto fora do template controlado
  - preencher fatos inexistentes
  - consultar fontes externas por conta própria
  - alterar diretamente o banco de dados

Estado: integrado com Anthropic Claude via config.LLM_ENABLED.
Se LLM_ENABLED=false ou ANTHROPIC_API_KEY ausente, delega ao
classification_helper determinístico como fallback seguro.
"""
from __future__ import annotations
import json
import logging
from copy import deepcopy
from time import perf_counter

import requests

_logger = logging.getLogger(__name__)

from soc_copilot.modules.classification_helper import analyze as deterministic_analyze
from soc_copilot.modules.rule_loader import RulePack
from soc_copilot.modules.soc_copilot_loader import build_prompt_context
from socc.gateway.llm_gateway import (
    inference_guard,
    record_inference_event,
    record_prompt_audit,
    resolve_auth_context,
    resolve_runtime,
)

# ---------------------------------------------------------------------------
# Schema de entrada obrigatório (o que _call_llm recebe)
# ---------------------------------------------------------------------------
INPUT_SCHEMA = {
    "fields": {
        "Horario": str,        # HH:MM:SS (já convertido para SP)
        "Usuario": str,
        "IP_Origem": str,
        "IP_Origem_Privado": bool,
        "Destino": str,
        "Caminho": str,
        "LogSource": str,
        "Assunto": str,
        "IOCs": dict,          # {ips_externos, ips_internos, urls, dominios, hashes}
    },
    "ti_results": dict,        # {ioc: resultado_resumido}
    "regras_consolidadas": dict,
    "classificacao_candidata": dict,
    "regra": str,
    "cliente": str,
    "modelo_aderente": dict,
}

# ---------------------------------------------------------------------------
# Schema obrigatório de saída (PRD Seção 7)
# ---------------------------------------------------------------------------
_OUTPUT_SCHEMA_KEYS = {
    "resumo_factual", "hipoteses", "lacunas",
    "classificacao_sugerida", "mitre_candidato",
    "modelo_sugerido", "blocos_recomendados",
    "proximos_passos", "alertas_de_qualidade",
}

# Tipos esperados por chave (para validação básica)
_OUTPUT_TYPES: dict[str, type] = {
    "resumo_factual": dict,
    "hipoteses": list,
    "lacunas": list,
    "classificacao_sugerida": dict,
    "mitre_candidato": dict,
    "modelo_sugerido": str,
    "blocos_recomendados": dict,
    "proximos_passos": list,
    "alertas_de_qualidade": list,
}

_OUTPUT_DEFAULTS = {
    "resumo_factual": {
        "o_que": "",
        "quem": [],
        "onde": [],
        "quando": "",
        "artefatos": [],
    },
    "hipoteses": [],
    "lacunas": [],
    "classificacao_sugerida": {"tipo": "", "confianca": 0.0, "racional": ""},
    "mitre_candidato": {"tecnica": "", "justificativa": ""},
    "modelo_sugerido": "",
    "blocos_recomendados": {
        "incluir_analise_ip": False,
        "incluir_referencia_mitre": False,
    },
    "proximos_passos": [],
    "alertas_de_qualidade": [],
}


def _make_output_defaults() -> dict:
    return deepcopy(_OUTPUT_DEFAULTS)


def _rule_context_from_pack(pack: RulePack | None) -> dict:
    if pack is None:
        return {
            "precedencia": [],
            "formatacao": {},
            "threat_intel": {},
            "estruturas_saida": {},
            "checklist_validacao": [],
            "excecao_cliente": {},
        }

    return {
        "precedencia": pack.precedence[:],
        "formatacao": pack.formatting_rules.copy(),
        "threat_intel": pack.threat_intel_rules.copy(),
        "estruturas_saida": {key: value[:] for key, value in pack.output_structures.items()},
        "checklist_validacao": pack.validation_checklist[:],
        "excecao_cliente": pack.client_exception.copy(),
    }


def _build_llm_input(
    fields: dict,
    ti_results: dict,
    regra: str,
    cliente: str,
    pack: RulePack | None,
    deterministic_result: dict,
    raw_text: str = "",
    knowledge_context: str = "",
    knowledge_sources: str = "",
) -> dict:
    soc_context = _build_soc_copilot_context(
        fields=fields,
        raw_text=raw_text,
        cliente=cliente,
        regra=regra,
        knowledge_context=knowledge_context,
        knowledge_sources=knowledge_sources,
    )
    return {
        "fields": fields,
        "ti_results": ti_results,
        "regras_consolidadas": _rule_context_from_pack(pack),
        "classificacao_candidata": deterministic_result.get("classificacao_sugerida", {}),
        "regra": regra,
        "cliente": cliente,
        "raw_text": raw_text,
        "modelo_aderente": {
            "nome": pack.modelo_nome if pack else "",
            "caminho": pack.modelo_metadata.caminho if pack else "",
            "score": pack.modelo_metadata.score if pack else 0,
            "matched_tokens": pack.modelo_metadata.matched_tokens[:] if pack else [],
        },
        "soc_copilot": soc_context,
    }


def _merge_nested_dict(base: dict, incoming: object, expected_fields: dict) -> dict:
    merged = deepcopy(base)
    if not isinstance(incoming, dict):
        return merged

    # Aceita "justificativa" como alias legado apenas na classificação sugerida.
    if "racional" in expected_fields and "racional" not in incoming and "justificativa" in incoming:
        incoming = {**incoming, "racional": incoming.get("justificativa", "")}

    for field, expected_type in expected_fields.items():
        value = incoming.get(field)
        if expected_type is float:
            if isinstance(value, (int, float)):
                merged[field] = float(value)
        elif isinstance(value, expected_type):
            merged[field] = value

    return merged


def _validate_output(data: object, fallback: dict | None = None) -> dict:
    """
    Garante que a saída respeita o schema obrigatório:
      1. Provider inválido cai para fallback seguro.
      2. Chaves ausentes recebem defaults seguros.
      3. Estruturas internas obrigatórias são normalizadas.
      4. Chaves fora do schema são removidas.
    """
    output = _make_output_defaults()
    validation_alerts: list[str] = []
    fallback = fallback if isinstance(fallback, dict) else {}
    provider_is_valid_dict = isinstance(data, dict)

    if not provider_is_valid_dict:
        validation_alerts.append(
            "Saída da semi-LLM inválida; aplicado fallback determinístico."
        )
        data = {}

    # Usa o fallback determinístico como base segura.
    for key in _OUTPUT_SCHEMA_KEYS:
        fallback_value = fallback.get(key)
        expected_type = _OUTPUT_TYPES[key]
        if isinstance(fallback_value, expected_type):
            output[key] = deepcopy(fallback_value)

    output["resumo_factual"] = _merge_nested_dict(
        output["resumo_factual"],
        output.get("resumo_factual"),
        {
            "o_que": str,
            "quem": list,
            "onde": list,
            "quando": str,
            "artefatos": list,
        },
    )
    output["classificacao_sugerida"] = _merge_nested_dict(
        output["classificacao_sugerida"],
        output.get("classificacao_sugerida"),
        {"tipo": str, "confianca": float, "racional": str},
    )
    output["mitre_candidato"] = _merge_nested_dict(
        output["mitre_candidato"],
        output.get("mitre_candidato"),
        {"tecnica": str, "justificativa": str},
    )
    output["blocos_recomendados"] = _merge_nested_dict(
        output["blocos_recomendados"],
        output.get("blocos_recomendados"),
        {"incluir_analise_ip": bool, "incluir_referencia_mitre": bool},
    )

    # Aplica o provider apenas se vier em formato esperado.
    if provider_is_valid_dict:
        for key in ("hipoteses", "lacunas", "proximos_passos", "alertas_de_qualidade"):
            value = data.get(key)
            if isinstance(value, list):
                output[key] = value

        if isinstance(data.get("modelo_sugerido"), str):
            output["modelo_sugerido"] = data["modelo_sugerido"]

        output["resumo_factual"] = _merge_nested_dict(
            output["resumo_factual"],
            data.get("resumo_factual"),
            {
                "o_que": str,
                "quem": list,
                "onde": list,
                "quando": str,
                "artefatos": list,
            },
        )
        output["classificacao_sugerida"] = _merge_nested_dict(
            output["classificacao_sugerida"],
            data.get("classificacao_sugerida"),
            {"tipo": str, "confianca": float, "racional": str},
        )
        output["mitre_candidato"] = _merge_nested_dict(
            output["mitre_candidato"],
            data.get("mitre_candidato"),
            {"tecnica": str, "justificativa": str},
        )
        output["blocos_recomendados"] = _merge_nested_dict(
            output["blocos_recomendados"],
            data.get("blocos_recomendados"),
            {"incluir_analise_ip": bool, "incluir_referencia_mitre": bool},
        )

    if validation_alerts:
        output["alertas_de_qualidade"].extend(validation_alerts)

    return {key: output[key] for key in _OUTPUT_SCHEMA_KEYS}


def _load_agent_rules_condensed() -> str:
    """Carrega versão condensada das regras do AGENT.md para o system prompt."""
    try:
        from soc_copilot import config as _cfg
        p = __import__("pathlib").Path(getattr(_cfg, "AGENT_MD", ""))
        if p.exists():
            text = p.read_text(encoding="utf-8")
            # Extrai apenas as seções críticas (regras obrigatórias + regras de escrita)
            lines = []
            in_section = False
            for line in text.splitlines():
                if line.startswith("## Regras obrigatórias") or line.startswith("## Regras de escrita") or line.startswith("## Regra MITRE"):
                    in_section = True
                elif line.startswith("## ") and in_section:
                    in_section = False
                if in_section or line.startswith("## Regras obrigatórias") or line.startswith("## Regras de escrita") or line.startswith("## Regra MITRE"):
                    lines.append(line)
            return "\n".join(lines)
    except Exception:
        pass
    return ""


def _infer_artifact_type(fields: dict, raw_text: str) -> str:
    format_hint = str(fields.get("_source_format", "")).lower()
    source_hint = str(fields.get("LogSource", "")).lower()
    subject_hint = str(fields.get("Assunto", "")).lower()
    combined = " ".join(
        part for part in (format_hint, source_hint, subject_hint, raw_text[:2000].lower()) if part
    )

    if any(token in combined for token in ("subject:", "reply-to", "attachment", "email", "mail")):
        return "email"
    if any(token in combined for token in ("http://", "https://", "www.", "domain", "url")):
        return "url"
    if any(
        token in combined
        for token in ("powershell", "cmd.exe", "rundll32", "schtasks", "registry", "persistence")
    ):
        return "malware"
    return "payload"


def _build_soc_copilot_context(
    fields: dict,
    raw_text: str,
    cliente: str,
    regra: str,
    knowledge_context: str = "",
    knowledge_sources: str = "",
) -> dict:
    artifact_type = _infer_artifact_type(fields, raw_text)
    seed_parts = []
    if cliente:
        seed_parts.append(f"Cliente: {cliente}")
    if regra:
        seed_parts.append(f"Regra: {regra}")
    assunto = str(fields.get("Assunto", "")).strip()
    if assunto:
        seed_parts.append(f"Assunto: {assunto}")
    seed_parts.append(raw_text[:2000] if raw_text else "")
    seed_input = "\n".join(part for part in seed_parts if part).strip()

    try:
        return build_prompt_context(
            user_input=seed_input or "payload de seguranca",
            artifact_type=artifact_type,
            session_context="",
            knowledge_context=knowledge_context,
            knowledge_sources=knowledge_sources,
        )
    except Exception:
        return {
            "identity": "",
            "soul": "",
            "user": "",
            "agents": "",
            "memory": "",
            "tools": "",
            "skills_index": "",
            "references_index": "",
            "evidence_rules": "",
            "ioc_extraction": "",
            "security_json_patterns": "",
            "telemetry_investigation_patterns": "",
            "mitre_guidance": "",
            "output_contract": "",
            "selected_skill": "payload-triage",
            "skill_content": "",
            "schema_path": "",
            "session_context": "",
            "knowledge_context": knowledge_context,
            "knowledge_sources": knowledge_sources,
            "user_input": seed_input,
        }


_SYSTEM_PROMPT_BASE = """\
Você é um analista especializado de SOC (Security Operations Center) da iT.eam, \
com expertise em análise de eventos de segurança em ambiente SOC multi-tenant.

Seu papel é analisar dados de alertas e o payload bruto do evento, corrigindo \
extrações incompletas e fornecendo análise técnica objetiva para auxiliar analistas.

REGRAS DO AGENTE iT.eam (AGENT.md):
- Use obrigatoriamente Português do Brasil com acentuação e cedilha corretas
- Horário exclusivamente em São Paulo, formato HH:MM:SS
- Nunca invente informações ausentes — use string vazia ou lista vazia
- Toda análise termina em exatamente uma categoria: True Positive, Benign True Positive, \
False Positive, True Negative ou Log Transmission Failure
- Para técnicas MITRE use apenas o formato exato T1234 ou T1234.001
- Confiança deve ser float entre 0.0 e 1.0
- NÃO use markdown (sem **, sem #, sem ```)
- Recomendações devem ser anônimas (sem usuários, IPs internos ou hostnames reais)
- Responda APENAS com JSON válido, sem texto adicional antes ou depois

INSTRUÇÕES DE EXTRAÇÃO:
- Analise TANTO os campos normalizados QUANTO o payload bruto
- Se um campo estiver como N/A nos campos normalizados, tente extraí-lo do payload bruto
- Usuário pode estar em: Username, user, srcuser, UserId, SubjectUserName, AccountName, email
- Horário pode estar em: time, timestamp, date+time, LogTime, CreationTime
- IP de origem: srcip, ClientIP, SourceAddress, RemoteAddress
- Assinatura/ataque: attack, msg, rulename, RuleName, Signature\
"""


def _build_system_prompt(llm_input: dict | None = None) -> str:
    """Monta system prompt com regras AGENT.md e persona do SOC Copilot."""
    extra = _load_agent_rules_condensed()
    soc_context = (llm_input or {}).get("soc_copilot", {}) if isinstance(llm_input, dict) else {}
    sections = [_SYSTEM_PROMPT_BASE]
    if extra:
        sections.append(f"REGRAS COMPLETAS DE ESCRITA (AGENT.md):\n{extra}")

    persona_sections = [
        soc_context.get("identity", ""),
        soc_context.get("soul", ""),
        soc_context.get("user", ""),
        soc_context.get("agents", ""),
        soc_context.get("memory", ""),
        soc_context.get("tools", ""),
        soc_context.get("evidence_rules", ""),
        soc_context.get("ioc_extraction", ""),
        soc_context.get("security_json_patterns", ""),
        soc_context.get("telemetry_investigation_patterns", ""),
        soc_context.get("mitre_guidance", ""),
        soc_context.get("output_contract", ""),
        f"Skill selecionada: {soc_context.get('selected_skill', '')}",
        soc_context.get("skill_content", ""),
    ]
    persona_text = "\n\n".join(section for section in persona_sections if section)
    if persona_text:
        sections.append(f"CONTEXTO DO SOC COPILOT:\n{persona_text}")

    sections.append(
        "DISCIPLINA DE SAIDA: responda apenas com JSON valido conforme o schema exigido, "
        "sem markdown, sem texto introdutorio e sem chaves extras."
    )
    return "\n\n".join(section for section in sections if section)

_USER_PROMPT_TEMPLATE = """\
Analise o evento de segurança abaixo e retorne um JSON estruturado.

SKILL DO SOC COPILOT:
{selected_skill}

ORIENTACAO DO PLAYBOOK:
{skill_content}

REGRAS DE EVIDENCIA:
{evidence_rules}

GUIA DE EXTRAÇÃO DE IOCS:
{ioc_extraction}

CATALOGO DE CAMPOS JSON DE SEGURANCA:
{security_json_patterns}

PADROES DE CONTEXTO INVESTIGATIVO:
{telemetry_investigation_patterns}

GUIA MITRE:
{mitre_guidance}

CONTRATO OFICIAL DE SAIDA:
{output_contract}

CONTEXTO RECUPERADO DA BASE LOCAL:
{knowledge_context}

DADOS DO EVENTO:
{payload_json}

Retorne APENAS um objeto JSON com exatamente estas chaves (sem chaves extras):
{{
  "resumo_factual": {{
    "o_que": "descrição técnica objetiva e concisa do que ocorreu",
    "quem": ["lista de atores/usuários envolvidos"],
    "onde": ["lista de sistemas, IPs ou destinos relevantes"],
    "quando": "horário do evento no formato HH:MM:SS",
    "artefatos": ["lista de IOCs ou artefatos técnicos identificados"]
  }},
  "hipoteses": [
    {{
      "tipo": "True Positive|False Positive|Benign True Positive|True Negative|Log Transmission Failure",
      "confianca": 0.0,
      "justificativa": "justificativa técnica objetiva para esta hipótese"
    }}
  ],
  "lacunas": ["lacuna de evidência que impede conclusão definitiva"],
  "classificacao_sugerida": {{
    "tipo": "classificação mais provável dentre os tipos válidos",
    "confianca": 0.0,
    "racional": "racional técnico detalhado para a sugestão"
  }},
  "mitre_candidato": {{
    "tecnica": "T1234 ou T1234.001 se aplicável, senão string vazia",
    "justificativa": "por que esta técnica MITRE se aplica ao comportamento observado"
  }},
  "modelo_sugerido": "nome do modelo de nota mais adequado para este caso",
  "blocos_recomendados": {{
    "incluir_analise_ip": true,
    "incluir_referencia_mitre": false
  }},
  "proximos_passos": ["ação recomendada ao analista (anonimizada)"],
  "alertas_de_qualidade": ["alerta sobre qualidade dos dados ou limitações da análise"]
}}
"""


# ---------------------------------------------------------------------------
# MCP Tools — definições e executor local para Ollama tool calling
# ---------------------------------------------------------------------------

_MCP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_agent_rules",
            "description": (
                "Retorna as regras obrigatórias do agente SOC iT.eam (AGENT.md). "
                "Use quando precisar verificar o formato correto de saída, "
                "regras de escrita ou exceções por cliente."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_relevant_model",
            "description": (
                "Retorna o conteúdo de um modelo de alerta existente como referência "
                "de estrutura e linguagem. Use para casos com tipo de ataque identificado."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "attack_name": {
                        "type": "string",
                        "description": "Nome do ataque, assinatura ou tipo de evento (ex: 'Botnet', 'Acesso RDP', 'Varredura').",
                    }
                },
                "required": ["attack_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_deterministic_analysis",
            "description": (
                "Retorna a análise determinística já calculada para este evento. "
                "Use para validar ou enriquecer sua classificação com a análise de base."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sop",
            "description": (
                "Retorna o Procedimento Operacional Standard (SOP.md) com as 5 etapas "
                "obrigatórias de análise. Use quando não tiver certeza do fluxo correto."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _execute_mcp_tool(name: str, arguments: dict, llm_input: dict) -> str:
    """Executa uma ferramenta MCP localmente e retorna o resultado como string."""
    try:
        if name == "get_agent_rules":
            rules = _load_agent_rules_condensed()
            return rules if rules else "AGENT.md não encontrado no caminho configurado."

        if name == "get_deterministic_analysis":
            fields = llm_input.get("fields", {})
            ti = llm_input.get("ti_results", {})
            raw = llm_input.get("raw_text", "")
            result = deterministic_analyze(fields, ti, raw)
            return json.dumps(result, ensure_ascii=False, indent=2)

        if name == "get_relevant_model":
            attack = (arguments.get("attack_name") or "").strip()
            from soc_copilot import config as _cfg
            from pathlib import Path as _Path
            modelos_dir = _Path(getattr(_cfg, "MODELOS_DIR", ""))
            if not modelos_dir.exists() or not attack:
                return "Modelo não encontrado."
            # Busca por similaridade simples de tokens
            attack_tokens = set(attack.lower().replace(".", " ").replace("_", " ").split())
            best_score, best_path = 0, None
            for f in modelos_dir.iterdir():
                if not f.is_file():
                    continue
                name_tokens = set(f.name.lower().replace("-", " ").replace("_", " ").split())
                score = len(attack_tokens & name_tokens)
                if score > best_score:
                    best_score, best_path = score, f
            if best_path and best_score > 0:
                try:
                    return best_path.read_text(encoding="utf-8", errors="ignore")[:3000]
                except Exception:
                    pass
            return "Nenhum modelo compatível encontrado para o ataque informado."

        if name == "get_sop":
            from soc_copilot import config as _cfg
            from pathlib import Path as _Path
            p = _Path(getattr(_cfg, "SOP_MD", ""))
            return p.read_text(encoding="utf-8")[:4000] if p.exists() else "SOP.md não encontrado."

        return f"Ferramenta '{name}' não reconhecida."
    except Exception as exc:
        return f"Erro ao executar ferramenta '{name}': {exc}"


def _is_quality_sufficient(result: dict) -> bool:
    """
    Verifica se o output do LLM tem qualidade mínima para uso.
    Retorna False se o output deve ser descartado e o fallback ativado.
    """
    if not isinstance(result, dict):
        return False
    # hipoteses deve existir e ter ao menos 1 entrada
    if not isinstance(result.get("hipoteses"), list) or not result["hipoteses"]:
        return False
    # classificacao_sugerida com confiança válida
    cls = result.get("classificacao_sugerida", {})
    if not isinstance(cls, dict):
        return False
    confianca = cls.get("confianca", 0)
    if not isinstance(confianca, (int, float)) or confianca <= 0:
        return False
    # o_que precisa ter conteúdo (pelo menos 15 chars)
    o_que = (result.get("resumo_factual") or {}).get("o_que", "")
    if len(str(o_que)) < 15:
        return False
    return True


def _call_llm_ollama_with_mcp(
    llm_input: dict,
    fallback_analysis: dict,
    cfg,
) -> dict:
    """
    Chama qwen3.5:9b (ou modelo Ollama configurado) com tool calling MCP.

    Fluxo:
      1. Injeta contexto MCP (agent_rules + análise determinística) no prompt
      2. Oferece 4 ferramentas ao modelo para lookups dinâmicos
      3. Executa loop agêntico (max 4 turns) com execução local das tools
      4. Valida qualidade do output
      5. Se qualidade insuficiente → chama Claude como fallback
    """
    import requests as _requests

    runtime = resolve_runtime()
    model = getattr(cfg, "OLLAMA_MODEL", "qwen3.5:9b")
    base_url = getattr(cfg, "OLLAMA_URL", "http://localhost:11434").rstrip("/")
    timeout = float(getattr(cfg, "LLM_TIMEOUT", 90))

    # --- Contexto MCP pré-injetado (reduz dependência de tool calling) ---
    agent_rules = _load_agent_rules_condensed()
    det_analysis = json.dumps(
        llm_input.get("classificacao_candidata", {}), ensure_ascii=False
    )

    fields = llm_input.get("fields", {})
    iocs = fields.get("IOCs", {})
    raw_payload = llm_input.get("raw_text", "")

    mcp_context = ""
    if agent_rules:
        mcp_context += f"\nREGRAS DO AGENTE (AGENT.md):\n{agent_rules}\n"
    if det_analysis and det_analysis != "{}":
        mcp_context += f"\nANÁLISE DETERMINÍSTICA DE BASE:\n{det_analysis}\n"

    payload_summary = {
        "regra": llm_input.get("regra", ""),
        "cliente": llm_input.get("cliente", ""),
        "skill_selecionada": (llm_input.get("soc_copilot", {}) or {}).get("selected_skill", ""),
        "campos_normalizados": {k: v for k, v in fields.items() if k != "IOCs"},
        "iocs_identificados": {
            "ips_externos": iocs.get("ips_externos", []),
            "ips_internos": iocs.get("ips_internos", []),
            "dominios": iocs.get("dominios", []),
            "hashes": iocs.get("hashes", []),
            "urls": iocs.get("urls", []),
        },
        "ti_results": llm_input.get("ti_results", {}),
        "payload_bruto": raw_payload[:3000] if raw_payload else "",
    }

    user_content = (
        f"{mcp_context}\n"
        + _USER_PROMPT_TEMPLATE.format(
            selected_skill=(llm_input.get("soc_copilot", {}) or {}).get("selected_skill", ""),
            skill_content=(llm_input.get("soc_copilot", {}) or {}).get("skill_content", ""),
            evidence_rules=(llm_input.get("soc_copilot", {}) or {}).get("evidence_rules", ""),
            ioc_extraction=(llm_input.get("soc_copilot", {}) or {}).get("ioc_extraction", ""),
            security_json_patterns=(llm_input.get("soc_copilot", {}) or {}).get("security_json_patterns", ""),
            telemetry_investigation_patterns=(llm_input.get("soc_copilot", {}) or {}).get("telemetry_investigation_patterns", ""),
            mitre_guidance=(llm_input.get("soc_copilot", {}) or {}).get("mitre_guidance", ""),
            output_contract=(llm_input.get("soc_copilot", {}) or {}).get("output_contract", ""),
            knowledge_context=(llm_input.get("soc_copilot", {}) or {}).get("knowledge_context", ""),
            payload_json=json.dumps(payload_summary, ensure_ascii=False, indent=2),
        )
    )
    record_prompt_audit(
        source="semi_llm_adapter",
        provider="ollama",
        model=model,
        prompt_text=_build_system_prompt(llm_input) + "\n\n" + user_content,
        skill=(llm_input.get("soc_copilot", {}) or {}).get("selected_skill", ""),
    )

    messages = [
        {"role": "system", "content": _build_system_prompt(llm_input)},
        {"role": "user",   "content": user_content},
    ]

    MAX_TURNS = 4
    raw_result = None
    started = perf_counter()

    try:
        for turn in range(MAX_TURNS):
            body: dict = {
                "model": model,
                "messages": messages,
                "stream": False,
                "tools": _MCP_TOOLS,
                "options": {"temperature": 0.1},
            }

            resp = _requests.post(
                f"{base_url}/api/chat",
                json=body,
                timeout=timeout,
            )
            resp.raise_for_status()
            resp_data = resp.json()
            msg = resp_data.get("message", {})

            tool_calls = msg.get("tool_calls", [])

            if tool_calls:
                # Modelo pediu tools — executar e continuar o loop
                messages.append({"role": "assistant", "content": msg.get("content", ""), "tool_calls": tool_calls})
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    tool_name = fn.get("name", "")
                    tool_args = fn.get("arguments", {})
                    if isinstance(tool_args, str):
                        try:
                            tool_args = json.loads(tool_args)
                        except Exception:
                            tool_args = {}
                    tool_result = _execute_mcp_tool(tool_name, tool_args, llm_input)
                    _logger.info("MCP tool chamada: %s → %d chars de resultado.", tool_name, len(tool_result))
                    messages.append({"role": "tool", "content": tool_result})
                # Solicitar resposta final após tools
                if turn == MAX_TURNS - 2:
                    messages.append({
                        "role": "user",
                        "content": "Com base nas informações das ferramentas, retorne APENAS o JSON final conforme o schema solicitado.",
                    })
            else:
                # Resposta final — tentar parsear JSON
                content = msg.get("content", "").strip()
                # Remove blocos markdown se houver
                if content.startswith("```"):
                    parts = content.split("```")
                    content = parts[1] if len(parts) > 1 else content
                    if content.startswith("json"):
                        content = content[4:].lstrip()
                try:
                    raw_result = json.loads(content)
                    break
                except json.JSONDecodeError:
                    # Tentativa de extração de JSON embutido
                    import re as _re
                    m = _re.search(r'\{[\s\S]*\}', content)
                    if m:
                        try:
                            raw_result = json.loads(m.group())
                            break
                        except Exception:
                            pass
                    _logger.warning("Ollama turn %d: JSON inválido na resposta.", turn + 1)
                    # Última tentativa: pedir explicitamente JSON
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": "Retorne APENAS JSON válido conforme o schema, sem texto adicional."})

    except Exception as exc:
        _logger.error("Falha no Ollama MCP (%s): %s; ativando fallback Claude.", model, exc)
        record_inference_event(
            source="semi_llm_adapter",
            provider="ollama",
            model=model,
            requested_device=runtime.device,
            effective_device=runtime.device,
            latency_ms=(perf_counter() - started) * 1000,
            success=False,
            fallback_used=True,
            error=str(exc),
        )
        raw_result = None

    # --- Validação de qualidade ---
    if raw_result is not None and _is_quality_sufficient(raw_result):
        _logger.info("Ollama/%s — qualidade OK, resultado aceito.", model)
        record_inference_event(
            source="semi_llm_adapter",
            provider="ollama",
            model=model,
            requested_device=runtime.device,
            effective_device=runtime.device,
            latency_ms=(perf_counter() - started) * 1000,
            success=True,
            fallback_used=False,
        )
        return raw_result

    _logger.warning(
        "Ollama/%s — qualidade insuficiente ou JSON inválido. Ativando fallback Claude.",
        model,
    )
    record_inference_event(
        source="semi_llm_adapter",
        provider="ollama",
        model=model,
        requested_device=runtime.device,
        effective_device=runtime.device,
        latency_ms=(perf_counter() - started) * 1000,
        success=False,
        fallback_used=True,
        error="quality_insufficient_or_invalid_json",
    )
    return _call_llm_anthropic(llm_input, fallback_analysis, cfg, fallback_used=True)


def _call_llm_anthropic(
    llm_input: dict,
    fallback_analysis: dict,
    cfg,
    fallback_used: bool = False,
) -> dict:
    """
    Chama o Claude via API Anthropic (nuvem).
    """
    auth = resolve_auth_context("anthropic")
    api_key = str(auth.get("credential") or getattr(cfg, "ANTHROPIC_API_KEY", ""))
    auth_method = str(auth.get("method") or "api_key")
    if not api_key:
        try:
            from socc.gateway.llm_gateway import resolve_api_key
            api_key = resolve_api_key("anthropic")
        except Exception:
            pass
    if not api_key:
        _logger.warning("ANTHROPIC_API_KEY não configurada; usando análise determinística.")
        record_inference_event(
            source="semi_llm_adapter",
            provider="anthropic",
            model=getattr(cfg, "LLM_MODEL", "claude-haiku-4-5-20251001"),
            requested_device="gpu" if resolve_runtime().gpu_available else "cpu",
            effective_device="remote",
            latency_ms=0,
            success=False,
            fallback_used=fallback_used,
            error="missing_api_key",
        )
        return fallback_analysis

    model = getattr(cfg, "LLM_MODEL", "claude-haiku-4-5-20251001")
    timeout = float(getattr(cfg, "LLM_TIMEOUT", 30))
    started = perf_counter()

    fields = llm_input.get("fields", {})
    iocs = fields.get("IOCs", {})
    raw_payload = llm_input.get("raw_text", "")

    payload_summary = {
        "regra": llm_input.get("regra", ""),
        "cliente": llm_input.get("cliente", ""),
        "skill_selecionada": (llm_input.get("soc_copilot", {}) or {}).get("selected_skill", ""),
        "campos_normalizados": {k: v for k, v in fields.items() if k != "IOCs"},
        "iocs_identificados": {
            "ips_externos": iocs.get("ips_externos", []),
            "ips_internos": iocs.get("ips_internos", []),
            "dominios": iocs.get("dominios", []),
            "hashes": iocs.get("hashes", []),
            "urls": iocs.get("urls", []),
        },
        "ti_results": llm_input.get("ti_results", {}),
        "classificacao_candidata_deterministica": llm_input.get("classificacao_candidata", {}),
        "payload_bruto": raw_payload[:3000] if raw_payload else "",
    }

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        selected_skill=(llm_input.get("soc_copilot", {}) or {}).get("selected_skill", ""),
        skill_content=(llm_input.get("soc_copilot", {}) or {}).get("skill_content", ""),
        evidence_rules=(llm_input.get("soc_copilot", {}) or {}).get("evidence_rules", ""),
        ioc_extraction=(llm_input.get("soc_copilot", {}) or {}).get("ioc_extraction", ""),
        security_json_patterns=(llm_input.get("soc_copilot", {}) or {}).get("security_json_patterns", ""),
        telemetry_investigation_patterns=(llm_input.get("soc_copilot", {}) or {}).get("telemetry_investigation_patterns", ""),
        mitre_guidance=(llm_input.get("soc_copilot", {}) or {}).get("mitre_guidance", ""),
        output_contract=(llm_input.get("soc_copilot", {}) or {}).get("output_contract", ""),
        knowledge_context=(llm_input.get("soc_copilot", {}) or {}).get("knowledge_context", ""),
        payload_json=json.dumps(payload_summary, ensure_ascii=False, indent=2),
    )
    record_prompt_audit(
        source="semi_llm_adapter",
        provider="anthropic",
        model=model,
        prompt_text=_build_system_prompt(llm_input) + "\n\n" + user_prompt,
        skill=(llm_input.get("soc_copilot", {}) or {}).get("selected_skill", ""),
    )

    try:
        if auth_method == "oauth":
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 2048,
                    "system": _build_system_prompt(llm_input),
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            response_text = "".join(
                str(item.get("text") or "")
                for item in list(payload.get("content") or [])
                if isinstance(item, dict) and str(item.get("type") or "") == "text"
            ).strip()
        else:
            try:
                import anthropic as _anthropic
            except ImportError:
                _logger.error("Pacote 'anthropic' não instalado; usando análise determinística.")
                record_inference_event(
                    source="semi_llm_adapter",
                    provider="anthropic",
                    model=getattr(cfg, "LLM_MODEL", "claude-haiku-4-5-20251001"),
                    requested_device="gpu" if resolve_runtime().gpu_available else "cpu",
                    effective_device="remote",
                    latency_ms=0,
                    success=False,
                    fallback_used=fallback_used,
                    error="anthropic_package_missing",
                )
                return fallback_analysis

            client = _anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model=model,
                max_tokens=2048,
                system=_build_system_prompt(llm_input),
                messages=[{"role": "user", "content": user_prompt}],
                timeout=timeout,
            )
            response_text = message.content[0].text.strip()
        if response_text.startswith("```"):
            parts = response_text.split("```")
            response_text = parts[1] if len(parts) > 1 else response_text
            if response_text.startswith("json"):
                response_text = response_text[4:].lstrip()
        result = json.loads(response_text)
        _logger.info("Análise LLM concluída via Anthropic/%s.", model)
        record_inference_event(
            source="semi_llm_adapter",
            provider="anthropic",
            model=model,
            requested_device="gpu" if resolve_runtime().gpu_available else "cpu",
            effective_device="remote",
            latency_ms=(perf_counter() - started) * 1000,
            success=True,
            fallback_used=fallback_used,
        )
        return result
    except Exception as exc:
        _logger.error("Falha na chamada Anthropic (%s): %s; usando análise determinística.", model, exc)
        record_inference_event(
            source="semi_llm_adapter",
            provider="anthropic",
            model=model,
            requested_device="gpu" if resolve_runtime().gpu_available else "cpu",
            effective_device="remote",
            latency_ms=(perf_counter() - started) * 1000,
            success=False,
            fallback_used=fallback_used,
            error=str(exc),
        )
        return fallback_analysis


def _call_llm(
    llm_input: dict,
    fallback_analysis: dict,
) -> dict:
    """
    Roteia a chamada LLM para o provider configurado em LLM_PROVIDER:
      - "ollama"     : modelo local via Ollama (padrão)
      - "anthropic"  : Claude via API Anthropic (nuvem)
    Em caso de falha ou LLM desabilitado, retorna fallback_analysis (determinístico).
    """
    try:
        from soc_copilot import config as _cfg
    except ImportError:
        _logger.warning("Módulo config não encontrado; usando análise determinística.")
        return fallback_analysis

    if not getattr(_cfg, "LLM_ENABLED", False):
        return fallback_analysis

    runtime = resolve_runtime()
    with inference_guard(runtime) as (allowed, reason):
        if not allowed:
            record_inference_event(
                source="semi_llm_adapter",
                provider=runtime.provider,
                model=runtime.model,
                requested_device=runtime.device,
                effective_device=runtime.device,
                latency_ms=0,
                success=False,
                fallback_used=True,
                error=reason,
            )
            return fallback_analysis

    provider = getattr(_cfg, "LLM_PROVIDER", "ollama").lower()

    if provider == "anthropic":
        return _call_llm_anthropic(llm_input, fallback_analysis, _cfg)

    # padrão: ollama com MCP tools + fallback Claude automático
    return _call_llm_ollama_with_mcp(llm_input, fallback_analysis, _cfg)


# ---------------------------------------------------------------------------
# Ponto de entrada — chamado pelo main.py ANTES do draft_engine
# ---------------------------------------------------------------------------
def run(
    fields: dict,
    ti_results: dict,
    raw_text: str,
    regra: str = "",
    cliente: str = "",
    pack: RulePack | None = None,
    knowledge_context: str = "",
    knowledge_sources: str = "",
) -> dict:
    """
    Executa a análise semi-LLM e retorna o pacote estruturado validado.
    A saída deste módulo é INPUT para o draft_engine — nunca o texto final.
    """
    deterministic_result = deterministic_analyze(fields, ti_results, raw_text)
    llm_input = _build_llm_input(
        fields=fields,
        ti_results=ti_results,
        regra=regra,
        cliente=cliente,
        pack=pack,
        deterministic_result=deterministic_result,
        raw_text=raw_text,
        knowledge_context=knowledge_context,
        knowledge_sources=knowledge_sources,
    )
    raw_output = _call_llm(llm_input, deterministic_result)
    return _validate_output(raw_output, fallback=deterministic_result)
