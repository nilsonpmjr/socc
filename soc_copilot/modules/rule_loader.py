"""
rule_loader.py
Carrega e consolida as regras operacionais:
  - AGENT.md
  - TOOLS.md
  - SOP.md
  - Inventário do MVP
  - Exceções por cliente
  - Modelos em Modelos/
Expõe um objeto RulePack consolidado para o restante do sistema.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from soc_copilot.config import AGENT_MD, INVENTARIO_MD, MODELOS_DIR, SOP_MD, TOOLS_MD


RULE_PRECEDENCE = [
    "AGENT.md",
    "TOOLS.md",
    "SOP.md",
    "Modelos/<modelo_aderente>",
]

FORMATTING_RULES = {
    "language": "pt-BR",
    "plain_text_only": True,
    "markdown_forbidden": True,
    "accents_required": True,
    "timezone_body_format": "HH:MM:SS",
    "recommendation_must_be_anonymized": True,
}

THREAT_INTEL_RULES = {
    "single_ioc_strategy": "threat_check.py --dashboard",
    "batch_strategy": "batch.py",
    "private_ioc_default_behavior": "skip",
    "duplicate_queries_forbidden": True,
}

OUTPUT_STRUCTURES = {
    "TP": [
        "Prezados,",
        "Título",
        "Narrativa do Evento",
        "Detalhes do Evento",
        "Análise do IP",
        "Análise Técnica",
        "Em anexo o Payload.",
        "Referência",
        "Referência MITRE",
        "Recomendação",
    ],
    "BTP": [
        "Classificação Final",
        "Resumo Técnico",
        "Justificativa da benignidade",
        "Ação de encerramento",
    ],
    "FP_TN_LTF": [
        "Classificação Final",
        "Justificativa",
        "Ação recomendada",
    ],
}

VALIDATION_CHECKLIST = [
    "texto_em_portugues",
    "acentuacao_correta",
    "sem_markdown",
    "classificacao_presente",
    "timezone_convertido",
    "estrutura_compativel_com_tipo_saida",
    "analise_ip_apenas_quando_relevante",
    "analise_tecnica_presente_em_alerta_completo",
    "referencia_e_mitre_quando_aplicaveis",
    "recomendacao_anonimizada",
    "sem_dados_sensiveis_na_recomendacao",
    "excecao_por_cliente_respeitada",
    "modelo_aderente_utilizado_quando_disponivel",
]

KNOWN_CLIENT_EXCEPTIONS: dict[str, dict] = {
    "icatu": {
        "repasse_tecnico": True,
        "encerramento_automatico": False,
        "descricao": (
            "Gerar alerta de encaminhamento técnico mesmo em casos não confirmatórios. "
            "Manter classificação técnica real e deixar validação para o time do cliente."
        ),
        # Todos os casos não-TP viram repasse para Icatu.
        # draft_engine aplica isso via: is_icatu and cls != "TP"
    }
}


@dataclass
class ModeloMetadata:
    nome: str = ""
    caminho: str = ""
    score: int = 0
    matched_tokens: list[str] = field(default_factory=list)


@dataclass
class RulePack:
    agent_rules: str = ""
    tools_rules: str = ""
    sop_rules: str = ""
    inventory_rules: str = ""
    precedence: list[str] = field(default_factory=list)
    formatting_rules: dict = field(default_factory=dict)
    threat_intel_rules: dict = field(default_factory=dict)
    output_structures: dict = field(default_factory=dict)
    validation_checklist: list[str] = field(default_factory=list)
    client_exception: dict = field(default_factory=dict)
    modelo_aderente: str = ""
    modelo_nome: str = ""
    modelo_metadata: ModeloMetadata = field(default_factory=ModeloMetadata)
    is_icatu: bool = False


def _read_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().strip()


def _normalize_client(cliente: str) -> str:
    return _normalize_text(cliente)


def _tokenize(value: str) -> list[str]:
    normalized = _normalize_text(value)
    return [token for token in re.split(r"[^a-z0-9]+", normalized) if len(token) >= 3]


def _score_model(rule_tokens: list[str], client_tokens: list[str], model_name: str) -> tuple[int, list[str]]:
    model_norm = _normalize_text(model_name)
    matched_tokens: list[str] = []
    score = 0

    for token in rule_tokens:
        if token in model_norm:
            score += 3
            matched_tokens.append(token)

    for token in client_tokens:
        if token in model_norm:
            score += 4
            matched_tokens.append(token)

    if rule_tokens:
        full_rule = " ".join(rule_tokens)
        if full_rule and full_rule in model_norm:
            score += 6

    return score, sorted(set(matched_tokens))


def _find_modelo(regra: str, cliente: str) -> tuple[str, str, ModeloMetadata]:
    """
    Busca o modelo mais aderente em Modelos/ pelo nome da regra ou cliente.
    Retorna (conteudo, nome_arquivo, metadata).
    """
    if not MODELOS_DIR.exists():
        return "", "", ModeloMetadata()

    regra_tokens = _tokenize(regra)
    cliente_tokens = _tokenize(cliente)

    candidatos: list[tuple[int, Path, list[str]]] = []
    for modelo_path in MODELOS_DIR.iterdir():
        if not modelo_path.is_file():
            continue
        score, matched_tokens = _score_model(regra_tokens, cliente_tokens, modelo_path.name)
        if score > 0:
            candidatos.append((score, modelo_path, matched_tokens))

    if not candidatos:
        return "", "", ModeloMetadata()

    melhor_score, melhor_path, matched_tokens = max(candidatos, key=lambda x: (x[0], len(x[2]), -len(x[1].name)))
    conteudo = _read_safe(melhor_path)
    metadata = ModeloMetadata(
        nome=melhor_path.name,
        caminho=str(melhor_path),
        score=melhor_score,
        matched_tokens=matched_tokens,
    )
    return conteudo, melhor_path.name, metadata


def _load_client_exception(cliente_norm: str) -> dict:
    if not cliente_norm:
        return {}
    return KNOWN_CLIENT_EXCEPTIONS.get(cliente_norm, {}).copy()


def load(regra: str = "", cliente: str = "") -> RulePack:
    """
    Carrega e consolida todas as regras operacionais do MVP.
    """
    cliente_norm = _normalize_client(cliente)
    modelo_aderente, modelo_nome, modelo_metadata = _find_modelo(regra, cliente)

    pack = RulePack(
        agent_rules=_read_safe(AGENT_MD),
        tools_rules=_read_safe(TOOLS_MD),
        sop_rules=_read_safe(SOP_MD),
        inventory_rules=_read_safe(INVENTARIO_MD),
        precedence=RULE_PRECEDENCE.copy(),
        formatting_rules=FORMATTING_RULES.copy(),
        threat_intel_rules=THREAT_INTEL_RULES.copy(),
        output_structures={key: value[:] for key, value in OUTPUT_STRUCTURES.items()},
        validation_checklist=VALIDATION_CHECKLIST[:],
        client_exception=_load_client_exception(cliente_norm),
        modelo_aderente=modelo_aderente,
        modelo_nome=modelo_nome,
        modelo_metadata=modelo_metadata,
        is_icatu=cliente_norm == "icatu",
    )

    return pack
