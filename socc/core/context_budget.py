"""Context Budget Manager — controla orçamento de tokens por seção do prompt.

Resolve o problema de prompt bloat: o system prompt do SOCC injeta persona,
references, skills, histórico, KB e payload indiscriminadamente, estourando
a janela de contexto de modelos menores (llama3.2:3b = 8K, qwen3.5:9b = 32K).

Este módulo:
1. Estima tokens por seção com heurística rápida (~4 chars/token)
2. Calcula orçamento disponível baseado no modelo ativo
3. Trunca seções por prioridade (payload > skill > identity > history > ...)
4. Exporta métricas de utilização para observabilidade
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

# Heurística: ~4 chars por token para modelos multilíngues.
# Conservadora — melhor subestimar tokens disponíveis.
_CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class ModelProfile:
    """Perfil de janela de contexto de um modelo."""
    name: str
    context_window: int
    effective_window: int  # janela útil (desconta overhead de formatação)


@dataclass
class SectionBudget:
    """Orçamento e uso real de uma seção do prompt."""
    name: str
    priority: int          # menor = mais importante (nunca cortar)
    original_tokens: int   # tokens antes de truncagem
    budget_tokens: int     # tokens alocados
    final_tokens: int      # tokens após truncagem
    truncated: bool = False
    omitted: bool = False
    content: str = ""


@dataclass
class ContextBudgetResult:
    """Resultado do cálculo de orçamento."""
    model: str
    context_window: int
    effective_window: int
    reserved_output: int
    available_tokens: int
    total_prompt_tokens: int
    sections: list[SectionBudget] = field(default_factory=list)
    overflow: bool = False
    overflow_tokens: int = 0

    def metrics(self) -> dict[str, Any]:
        """Retorna métricas para logging/observabilidade."""
        return {
            "model": self.model,
            "context_window": self.context_window,
            "available_tokens": self.available_tokens,
            "total_prompt_tokens": self.total_prompt_tokens,
            "overflow": self.overflow,
            "overflow_tokens": self.overflow_tokens,
            "utilization_pct": round(
                (self.total_prompt_tokens / max(1, self.available_tokens)) * 100, 1
            ),
            "sections": {
                s.name: {
                    "original": s.original_tokens,
                    "final": s.final_tokens,
                    "truncated": s.truncated,
                    "omitted": s.omitted,
                }
                for s in self.sections
            },
        }


# --- Perfis de modelos conhecidos ---

_MODEL_PROFILES: dict[str, ModelProfile] = {}


def _register_profile(name: str, context_window: int, effective_window: int) -> None:
    _MODEL_PROFILES[name.lower()] = ModelProfile(
        name=name,
        context_window=context_window,
        effective_window=effective_window,
    )


# Modelos Ollama comuns
_register_profile("llama3.2:1b",    8192,   5500)
_register_profile("llama3.2:3b",    8192,   6000)
_register_profile("llama3.2:8b",    8192,   6000)
_register_profile("llama3.1:8b",    131072, 28000)
_register_profile("qwen3.5:9b",     32768,  28000)
_register_profile("qwen3.5:14b",    32768,  28000)
_register_profile("qwen2.5:7b",     32768,  28000)
_register_profile("qwen2.5:14b",    131072, 40000)
_register_profile("mistral:7b",     32768,  24000)
_register_profile("mixtral:8x7b",   32768,  24000)
_register_profile("gemma2:9b",      8192,   6000)
_register_profile("gemma2:27b",     8192,   6000)
_register_profile("phi3:mini",      4096,   3000)
_register_profile("phi3:medium",    131072, 40000)
_register_profile("deepseek-r1:8b", 65536,  30000)

# Modelos cloud (janela grande, budget generoso)
_register_profile("claude-haiku-4-5-20251001", 200000, 120000)
_register_profile("claude-sonnet-4-20250514",  200000, 120000)
_register_profile("gpt-4o",                    128000, 80000)
_register_profile("gpt-4o-mini",               128000, 80000)
_register_profile("gpt-5-codex",               256000, 120000)


# --- Prioridade de seções ---
# Menor número = mais importante = cortado por último

SECTION_PRIORITIES: dict[str, int] = {
    "payload":      1,   # input do usuário — nunca cortar
    "instruction":  2,   # regras de saída — essenciais
    "skill":        3,   # skill ativa — essencial pro comportamento
    "identity":     4,   # persona curta — importante
    "soul":         5,   # missão e princípios
    "history":      6,   # histórico da sessão — resumir se necessário
    "knowledge":    7,   # RAG / KB — truncar
    "references":   8,   # references operacionais — truncar/omitir parcialmente
    "user":         9,   # contexto do usuário/SOC
    "agents":       10,  # regras de coordenação
    "memory":       11,  # memória operacional — omitir se apertado
    "tools":        12,  # inventário de tools — omitir se apertado
    "vantage":      13,  # contexto Vantage — omitir se apertado
}

# Budget mínimo por seção (tokens) — abaixo disso, omitir
_SECTION_MINIMUMS: dict[str, int] = {
    "payload":     50,
    "instruction": 50,
    "skill":       100,
    "identity":    50,
    "soul":        80,
    "history":     0,    # pode ser vazio
    "knowledge":   0,
    "references":  0,
    "user":        0,
    "agents":      0,
    "memory":      0,
    "tools":       0,
    "vantage":     0,
}

# Percentual máximo do budget que cada seção pode consumir
_SECTION_MAX_PCT: dict[str, float] = {
    "payload":     0.35,
    "skill":       0.20,
    "references":  0.20,
    "history":     0.15,
    "knowledge":   0.10,
    "vantage":     0.08,
    "memory":      0.05,
}


def estimate_tokens(text: str) -> int:
    """Estimativa rápida de tokens. ~4 chars por token (heurística)."""
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)


def get_model_profile(model_name: str) -> ModelProfile:
    """Retorna perfil do modelo. Fallback conservador se desconhecido."""
    key = str(model_name or "").strip().lower()
    if key in _MODEL_PROFILES:
        return _MODEL_PROFILES[key]

    # Tenta match parcial (ex: "qwen3.5:9b-q4_K_M" → "qwen3.5:9b")
    for profile_key, profile in _MODEL_PROFILES.items():
        if key.startswith(profile_key) or profile_key.startswith(key.split(":")[0]):
            return profile

    # Fallback conservador: assume 8K context
    _logger.debug("Modelo '%s' não tem perfil registrado, usando fallback 8K.", model_name)
    return ModelProfile(
        name=model_name or "unknown",
        context_window=8192,
        effective_window=6000,
    )


def _reserved_output_tokens(response_mode: str) -> int:
    """Tokens reservados para geração de resposta."""
    mode = str(response_mode or "balanced").strip().lower()
    return {
        "fast":     1024,
        "balanced": 4096,
        "deep":     8192,
    }.get(mode, 4096)


def _truncate_text(text: str, max_tokens: int) -> tuple[str, bool]:
    """Trunca texto para caber no orçamento de tokens."""
    if not text:
        return "", False
    current = estimate_tokens(text)
    if current <= max_tokens:
        return text, False

    # Trunca por caracteres (heurística)
    max_chars = max_tokens * _CHARS_PER_TOKEN
    truncated = text[:max_chars].strip()

    # Tenta cortar em boundary de parágrafo ou linha
    last_newline = truncated.rfind("\n")
    if last_newline > max_chars * 0.7:
        truncated = truncated[:last_newline].strip()

    truncated += "\n\n[... conteúdo truncado pelo budget de contexto ...]"
    return truncated, True


def _select_references(
    references: dict[str, str],
    user_input: str,
    max_tokens: int,
) -> dict[str, str]:
    """Seleciona references mais relevantes para o input dentro do budget."""
    if not references:
        return {}

    # Relevância por keyword matching simples
    input_lower = (user_input or "").lower()
    scored: list[tuple[str, str, float]] = []

    for name, content in references.items():
        score = 0.0
        name_lower = name.lower().replace("-", " ").replace("_", " ")

        # Boost por presença de keywords do nome no input
        for word in name_lower.split():
            if word in input_lower:
                score += 2.0

        # References essenciais sempre pontuam alto
        if name in ("output-contract", "evidence-rules"):
            score += 5.0
        elif name in ("ioc-extraction", "mitre-guidance"):
            score += 3.0

        # Penaliza por tamanho (references grandes custam mais)
        tokens = estimate_tokens(content)
        score -= tokens / 5000  # penalidade gradual

        scored.append((name, content, score))

    # Ordena por score descendente
    scored.sort(key=lambda x: x[2], reverse=True)

    # Seleciona até caber no budget
    selected: dict[str, str] = {}
    remaining = max_tokens
    for name, content, _score in scored:
        tokens = estimate_tokens(content)
        if tokens <= remaining:
            selected[name] = content
            remaining -= tokens
        elif remaining > 200:
            # Trunca a reference para caber
            truncated, _ = _truncate_text(content, remaining - 50)
            if truncated:
                selected[name] = truncated
                remaining -= estimate_tokens(truncated)
            break
        else:
            break

    return selected


def compute_budget(
    *,
    model_name: str,
    response_mode: str = "balanced",
    sections: dict[str, str],
    references: dict[str, str] | None = None,
    user_input: str = "",
) -> ContextBudgetResult:
    """Calcula orçamento de contexto e trunca seções por prioridade.

    Args:
        model_name: nome do modelo ativo (ex: "llama3.2:3b")
        response_mode: "fast", "balanced" ou "deep"
        sections: dict de nome_seção → conteúdo textual
        references: dict de nome_ref → conteúdo (processadas separadamente)
        user_input: input do usuário (para scoring de relevância)

    Returns:
        ContextBudgetResult com seções truncadas e métricas
    """
    profile = get_model_profile(model_name)
    reserved = _reserved_output_tokens(response_mode)
    available = max(0, profile.effective_window - reserved)

    # Fase 1: estima tokens originais de cada seção
    section_budgets: list[SectionBudget] = []
    for name, content in sections.items():
        original_tokens = estimate_tokens(content)
        priority = SECTION_PRIORITIES.get(name, 50)
        section_budgets.append(SectionBudget(
            name=name,
            priority=priority,
            original_tokens=original_tokens,
            budget_tokens=original_tokens,
            final_tokens=original_tokens,
            content=content,
        ))

    # Fase 1.5: processa references com seleção por relevância
    if references:
        total_ref_tokens = sum(estimate_tokens(v) for v in references.values())
        max_ref_budget = int(available * _SECTION_MAX_PCT.get("references", 0.20))

        if total_ref_tokens > max_ref_budget:
            selected_refs = _select_references(references, user_input, max_ref_budget)
        else:
            selected_refs = references

        ref_content = "\n\n".join(
            f"### {name}\n{content}"
            for name, content in selected_refs.items()
        )
        ref_tokens = estimate_tokens(ref_content)
        section_budgets.append(SectionBudget(
            name="references",
            priority=SECTION_PRIORITIES.get("references", 8),
            original_tokens=sum(estimate_tokens(v) for v in references.values()),
            budget_tokens=ref_tokens,
            final_tokens=ref_tokens,
            truncated=ref_tokens < total_ref_tokens,
            content=ref_content,
        ))

    # Ordena por prioridade (maior número = menos importante = cortar primeiro)
    section_budgets.sort(key=lambda s: s.priority)

    # Fase 2: calcula uso total
    total_tokens = sum(s.final_tokens for s in section_budgets)

    # Fase 3: trunca se excede budget
    if total_tokens > available:
        overflow = total_tokens - available

        # Itera das seções menos importantes para as mais importantes
        for section in reversed(section_budgets):
            if overflow <= 0:
                break

            min_tokens = _SECTION_MINIMUMS.get(section.name, 0)
            reducible = max(0, section.final_tokens - min_tokens)

            if reducible <= 0:
                continue

            if reducible >= overflow:
                # Trunca parcialmente
                new_tokens = section.final_tokens - overflow
                truncated_content, was_truncated = _truncate_text(
                    section.content, new_tokens
                )
                section.content = truncated_content
                section.final_tokens = estimate_tokens(truncated_content)
                section.truncated = was_truncated
                overflow = 0
            else:
                # Omite a seção inteira (ou reduz ao mínimo)
                if min_tokens > 0:
                    truncated_content, _ = _truncate_text(section.content, min_tokens)
                    section.content = truncated_content
                    section.final_tokens = estimate_tokens(truncated_content)
                    section.truncated = True
                    overflow -= reducible
                else:
                    overflow -= section.final_tokens
                    section.content = ""
                    section.final_tokens = 0
                    section.omitted = True

        total_tokens = sum(s.final_tokens for s in section_budgets)

    result = ContextBudgetResult(
        model=model_name,
        context_window=profile.context_window,
        effective_window=profile.effective_window,
        reserved_output=reserved,
        available_tokens=available,
        total_prompt_tokens=total_tokens,
        sections=section_budgets,
        overflow=total_tokens > available,
        overflow_tokens=max(0, total_tokens - available),
    )

    _logger.debug(
        "Context budget: model=%s available=%d used=%d (%.0f%%) overflow=%s",
        model_name,
        available,
        total_tokens,
        (total_tokens / max(1, available)) * 100,
        result.overflow,
    )
    for section in section_budgets:
        if section.truncated or section.omitted:
            _logger.debug(
                "  Section '%s': %d → %d tokens (%s)",
                section.name,
                section.original_tokens,
                section.final_tokens,
                "omitted" if section.omitted else "truncated",
            )

    return result


def apply_budget_to_prompt_context(
    *,
    model_name: str,
    response_mode: str,
    context: dict[str, str],
    user_input: str = "",
) -> tuple[dict[str, str], ContextBudgetResult]:
    """Aplica orçamento de contexto ao dict de contexto do prompt.

    Recebe o context dict produzido por build_prompt_context() e retorna
    uma versão com seções truncadas/omitidas conforme budget do modelo.

    Returns:
        (context_ajustado, budget_result)
    """
    # Separa references do resto das seções
    reference_keys = {
        "evidence_rules", "ioc_extraction", "security_json_patterns",
        "telemetry_investigation_patterns", "mitre_guidance", "output_contract",
    }
    ref_key_to_name = {
        "evidence_rules": "evidence-rules",
        "ioc_extraction": "ioc-extraction",
        "security_json_patterns": "security-json-patterns",
        "telemetry_investigation_patterns": "telemetry-investigation-patterns",
        "mitre_guidance": "mitre-guidance",
        "output_contract": "output-contract",
    }

    references: dict[str, str] = {}
    sections: dict[str, str] = {}

    for key, value in context.items():
        if key in reference_keys:
            ref_name = ref_key_to_name.get(key, key)
            if value:
                references[ref_name] = value
        elif key in ("selected_skill", "schema_path", "references_index",
                      "skills_index", "knowledge_sources", "user_input"):
            continue  # metadata, não seções de prompt
        elif value:
            # Mapeia chaves do context para nomes de seção do budget
            section_name = {
                "identity": "identity",
                "soul": "soul",
                "user": "user",
                "agents": "agents",
                "memory": "memory",
                "tools": "tools",
                "skill_content": "skill",
                "session_context": "history",
                "knowledge_context": "knowledge",
                "vantage_context": "vantage",
                "artifact_context": "payload",
                "artifact_hint": "payload",
            }.get(key)
            if section_name:
                if section_name in sections:
                    sections[section_name] = f"{sections[section_name]}\n\n{value}"
                else:
                    sections[section_name] = value

    budget = compute_budget(
        model_name=model_name,
        response_mode=response_mode,
        sections=sections,
        references=references,
        user_input=user_input,
    )

    # Reconstrói context com seções ajustadas
    adjusted = dict(context)

    # Aplica truncagem das seções
    section_map = {s.name: s for s in budget.sections}

    for key in list(adjusted.keys()):
        section_name = {
            "identity": "identity",
            "soul": "soul",
            "user": "user",
            "agents": "agents",
            "memory": "memory",
            "tools": "tools",
            "skill_content": "skill",
            "session_context": "history",
            "knowledge_context": "knowledge",
            "vantage_context": "vantage",
        }.get(key)

        if section_name and section_name in section_map:
            section = section_map[section_name]
            if section.omitted:
                adjusted[key] = ""
            elif section.truncated:
                # Para seções compostas (identity + soul compartilham "identity"),
                # trunca proporcionalmente
                adjusted[key] = section.content

    # Aplica references filtradas
    if "references" in section_map:
        ref_section = section_map["references"]
        if ref_section.omitted:
            for ref_key in reference_keys:
                adjusted[ref_key] = ""
        elif ref_section.truncated or ref_section.final_tokens < ref_section.original_tokens:
            # Reconstrói references individuais a partir do conteúdo selecionado
            # Simplificação: marca as que não foram selecionadas como vazias
            selected_ref_names = set()
            for line in ref_section.content.split("\n"):
                if line.startswith("### "):
                    selected_ref_names.add(line[4:].strip())

            name_to_key = {v: k for k, v in ref_key_to_name.items()}
            for ref_name, ref_key in name_to_key.items():
                if ref_name not in selected_ref_names:
                    adjusted[ref_key] = ""

    return adjusted, budget
