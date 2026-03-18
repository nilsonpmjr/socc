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

Estado atual: STUB — retorna o pacote do classification_helper sem LLM.
Para ativar a camada LLM real: implemente `_call_llm()` abaixo e ajuste
o provider/model em config.py.
"""
from __future__ import annotations
from copy import deepcopy

from soc_copilot.modules.classification_helper import analyze as deterministic_analyze
from soc_copilot.modules.rule_loader import RulePack

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
) -> dict:
    return {
        "fields": fields,
        "ti_results": ti_results,
        "regras_consolidadas": _rule_context_from_pack(pack),
        "classificacao_candidata": deterministic_result.get("classificacao_sugerida", {}),
        "regra": regra,
        "cliente": cliente,
        "modelo_aderente": {
            "nome": pack.modelo_nome if pack else "",
            "caminho": pack.modelo_metadata.caminho if pack else "",
            "score": pack.modelo_metadata.score if pack else 0,
            "matched_tokens": pack.modelo_metadata.matched_tokens[:] if pack else [],
        },
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


def _call_llm(
    llm_input: dict,
    fallback_analysis: dict,
) -> dict:
    """
    Stub: substitua este método quando um LLM local/API estiver disponível.
    Deve retornar um dict compatível com _OUTPUT_SCHEMA_KEYS.
    O LLM NÃO deve receber payload sensível intacto — apenas o pacote estruturado.
    """
    # TODO: integrar LLM (ex: claude-haiku local, ollama, etc.)
    # Enquanto o stub está ativo, delega ao classification_helper determinístico.
    return fallback_analysis


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
    )
    raw_output = _call_llm(llm_input, deterministic_result)
    return _validate_output(raw_output, fallback=deterministic_result)
