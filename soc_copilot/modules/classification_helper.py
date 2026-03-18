"""
classification_helper.py
Organiza os fatos observados, sugere hipóteses e lacunas,
e prepara o pacote de dados para o draft_engine.

No MVP, opera em modo determinístico:
  - pontua cada classificação candidata com base em sinais extraídos
  - aponta campos ausentes como lacunas
  - não toma decisão final (a classificação final é sempre do analista)

Quando o semi_llm_adapter estiver ativo, este módulo entrega os dados
estruturados para enriquecer a análise antes do draft.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Sinais simples para pontuação de hipóteses (regras determinísticas)
# ---------------------------------------------------------------------------
_LTF_SIGNALS = [
    "log transmission failure", "ltf", "sem eventos", "no events",
    "falha na coleta", "log gap",
]
_FP_SIGNALS = [
    "scanner interno", "monitoramento", "backup", "gmud", "change management",
    "vulnerability scan", "nessus", "qualys",
]
_BTP_SIGNALS = [
    "atividade esperada", "admin", "administrador", "autorizado", "whitelist",
    "legitimo", "legítimo",
]


def _score_hipoteses(fields: dict, raw_text: str) -> list[dict]:
    raw_lower = raw_text.lower()
    hipoteses = []

    # Log Transmission Failure
    ltf_score = sum(1 for s in _LTF_SIGNALS if s in raw_lower)
    if ltf_score:
        hipoteses.append({
            "tipo": "Log Transmission Failure",
            "confianca": min(round(ltf_score * 0.4, 2), 0.9),
            "justificativa": "Sinais de falha de transmissão de log detectados no payload.",
        })

    # False Positive
    fp_score = sum(1 for s in _FP_SIGNALS if s in raw_lower)
    if fp_score:
        hipoteses.append({
            "tipo": "False Positive",
            "confianca": min(round(fp_score * 0.3, 2), 0.8),
            "justificativa": "Payload contém termos associados a ferramentas/processos internos conhecidos.",
        })

    # Benign True Positive
    btp_score = sum(1 for s in _BTP_SIGNALS if s in raw_lower)
    if btp_score:
        hipoteses.append({
            "tipo": "Benign True Positive",
            "confianca": min(round(btp_score * 0.35, 2), 0.85),
            "justificativa": "Atividade parece legítima mas corretamente disparada pela regra.",
        })

    # True Positive (qualquer IOC externo consultável: IP, domínio ou hash)
    iocs = fields.get("IOCs", {})
    tem_ioc_ext = bool(
        iocs.get("ips_externos") or iocs.get("dominios") or iocs.get("hashes")
    )
    if tem_ioc_ext:
        tipos_ioc = []
        if iocs.get("ips_externos"):
            tipos_ioc.append("IP externo")
        if iocs.get("dominios"):
            tipos_ioc.append("domínio")
        if iocs.get("hashes"):
            tipos_ioc.append("hash")
        hipoteses.append({
            "tipo": "True Positive",
            "confianca": 0.5,
            "justificativa": (
                f"{', '.join(tipos_ioc)} identificado(s) no payload; "
                "reputação TI necessária para confirmar."
            ),
        })

    return sorted(hipoteses, key=lambda h: h["confianca"], reverse=True)


def _aponta_lacunas(fields: dict, ti_results: dict) -> list[str]:
    lacunas = []
    for campo in ["Horario", "Usuario", "IP_Origem", "LogSource"]:
        if fields.get(campo) == "N/A":
            lacunas.append(f"Campo '{campo}' ausente no payload.")

    iocs = fields.get("IOCs", {})
    tem_consultavel = bool(
        iocs.get("ips_externos") or iocs.get("dominios") or iocs.get("hashes")
    )
    if tem_consultavel and not ti_results:
        lacunas.append("IOCs externos identificados, mas consulta TI não realizada.")
    return lacunas


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------
def analyze(fields: dict, ti_results: dict, raw_text: str) -> dict:
    """
    Retorna o pacote estruturado de apoio à análise.
    Não decide a classificação final — apenas sugere.
    """
    hipoteses = _score_hipoteses(fields, raw_text)
    lacunas = _aponta_lacunas(fields, ti_results)

    classificacao_sugerida = hipoteses[0] if hipoteses else {
        "tipo": "indefinido",
        "confianca": 0.0,
        "racional": "Sem sinais suficientes para sugestão automática.",
    }

    return {
        "resumo_factual": {
            "o_que": "Evento detectado pela regra de monitoramento.",
            "quem": [fields.get("Usuario", "N/A")],
            "onde": [fields.get("IP_Origem", "N/A"), fields.get("Destino", "N/A")],
            "quando": fields.get("Horario", "N/A"),
            "artefatos": fields.get("IOCs", {}).get("ips_externos", []),
        },
        "hipoteses": hipoteses,
        "lacunas": lacunas,
        "classificacao_sugerida": classificacao_sugerida,
        "mitre_candidato": {"tecnica": "", "justificativa": ""},
        "modelo_sugerido": "",
        "blocos_recomendados": {
            "incluir_analise_ip": bool(ti_results),
            "incluir_referencia_mitre": False,
        },
        "proximos_passos": [],
        "alertas_de_qualidade": [],
    }
