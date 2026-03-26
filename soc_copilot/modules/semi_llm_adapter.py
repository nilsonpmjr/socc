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

_logger = logging.getLogger(__name__)

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


_SYSTEM_PROMPT = """\
Você é um assistente especializado de SOC (Security Operations Center), \
com expertise em análise de eventos de segurança.

Seu papel é analisar dados estruturados de alertas e fornecer análise técnica \
objetiva para auxiliar analistas SOC na tomada de decisão.

REGRAS OBRIGATÓRIAS:
- Responda APENAS com JSON válido, sem texto adicional, sem markdown
- Todos os campos de texto devem estar em Português do Brasil
- Acentuação e cedilha obrigatórias (ex: análise, ação, não)
- NÃO invente fatos que não estejam presentes nos dados fornecidos
- NÃO tome a decisão final de classificação — apenas sugira com nível de confiança
- NÃO use markdown (sem **, sem #, sem ```)
- Mantenha anonimização: não repita nomes de usuários em recomendações
- Para técnicas MITRE, use apenas o formato exato T1234 ou T1234.001
- Confiança deve ser float entre 0.0 e 1.0\
"""

_USER_PROMPT_TEMPLATE = """\
Analise o evento de segurança abaixo e retorne um JSON estruturado.

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


def _call_llm_ollama(
    llm_input: dict,
    fallback_analysis: dict,
    cfg,
) -> dict:
    """
    Chama um modelo local via Ollama (http://localhost:11434).
    Usa format="json" para forçar saída JSON estruturada.
    """
    import requests as _requests

    model = getattr(cfg, "OLLAMA_MODEL", "llama3.1:8b")
    base_url = getattr(cfg, "OLLAMA_URL", "http://localhost:11434").rstrip("/")
    timeout = float(getattr(cfg, "LLM_TIMEOUT", 60))

    fields = llm_input.get("fields", {})
    iocs = fields.get("IOCs", {})
    payload_summary = {
        "regra": llm_input.get("regra", ""),
        "cliente": llm_input.get("cliente", ""),
        "campos_normalizados": {k: v for k, v in fields.items() if k != "IOCs"},
        "iocs_identificados": {
            "ips_externos": iocs.get("ips_externos", []),
            "dominios": iocs.get("dominios", []),
            "hashes": iocs.get("hashes", []),
        },
        "ti_results": llm_input.get("ti_results", {}),
        "classificacao_candidata_deterministica": llm_input.get("classificacao_candidata", {}),
    }

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        payload_json=json.dumps(payload_summary, ensure_ascii=False, indent=2)
    )

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1},
    }

    try:
        resp = _requests.post(
            f"{base_url}/api/chat",
            json=body,
            timeout=timeout,
        )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
        result = json.loads(content)
        _logger.info("Análise LLM local concluída via Ollama/%s.", model)
        return result
    except Exception as exc:
        _logger.error("Falha no Ollama (%s): %s; usando análise determinística.", model, exc)
        return fallback_analysis


def _call_llm_anthropic(
    llm_input: dict,
    fallback_analysis: dict,
    cfg,
) -> dict:
    """
    Chama o Claude via API Anthropic (nuvem).
    """
    api_key = getattr(cfg, "ANTHROPIC_API_KEY", "")
    if not api_key:
        _logger.warning("ANTHROPIC_API_KEY não configurada; usando análise determinística.")
        return fallback_analysis

    try:
        import anthropic as _anthropic
    except ImportError:
        _logger.error("Pacote 'anthropic' não instalado; usando análise determinística.")
        return fallback_analysis

    model = getattr(cfg, "LLM_MODEL", "claude-haiku-4-5-20251001")
    timeout = float(getattr(cfg, "LLM_TIMEOUT", 30))

    fields = llm_input.get("fields", {})
    iocs = fields.get("IOCs", {})
    payload_summary = {
        "regra": llm_input.get("regra", ""),
        "cliente": llm_input.get("cliente", ""),
        "campos_normalizados": {k: v for k, v in fields.items() if k != "IOCs"},
        "iocs_identificados": {
            "ips_externos": iocs.get("ips_externos", []),
            "dominios": iocs.get("dominios", []),
            "hashes": iocs.get("hashes", []),
        },
        "ti_results": llm_input.get("ti_results", {}),
        "classificacao_candidata_deterministica": llm_input.get("classificacao_candidata", {}),
    }

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        payload_json=json.dumps(payload_summary, ensure_ascii=False, indent=2)
    )

    try:
        client = _anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
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
        return result
    except Exception as exc:
        _logger.error("Falha na chamada Anthropic (%s): %s; usando análise determinística.", model, exc)
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

    provider = getattr(_cfg, "LLM_PROVIDER", "ollama").lower()

    if provider == "anthropic":
        return _call_llm_anthropic(llm_input, fallback_analysis, _cfg)

    # padrão: ollama
    return _call_llm_ollama(llm_input, fallback_analysis, _cfg)


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
