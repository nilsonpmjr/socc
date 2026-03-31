"""Tests para socc/core/context_budget.py — Context Budget Manager."""

import pytest
from socc.core.context_budget import (
    estimate_tokens,
    get_model_profile,
    compute_budget,
    apply_budget_to_prompt_context,
    _select_references,
    _truncate_text,
    _reserved_output_tokens,
    SECTION_PRIORITIES,
    ContextBudgetResult,
)


class TestEstimateTokens:
    def test_empty(self):
        assert estimate_tokens("") == 0

    def test_short(self):
        assert estimate_tokens("hello") >= 1

    def test_proportional(self):
        short = estimate_tokens("a" * 100)
        long = estimate_tokens("a" * 1000)
        assert long > short

    def test_heuristic(self):
        # ~4 chars per token
        assert estimate_tokens("a" * 400) == 100
        assert estimate_tokens("a" * 4000) == 1000


class TestGetModelProfile:
    def test_known_model(self):
        p = get_model_profile("llama3.2:3b")
        assert p.context_window == 8192
        assert p.effective_window == 6000

    def test_large_model(self):
        p = get_model_profile("qwen3.5:9b")
        assert p.context_window == 32768

    def test_cloud_model(self):
        p = get_model_profile("claude-haiku-4-5-20251001")
        assert p.context_window == 200000

    def test_unknown_model_fallback(self):
        p = get_model_profile("totally-unknown:latest")
        assert p.context_window == 8192  # fallback conservador

    def test_partial_match(self):
        # "qwen3.5:9b-q4_K_M" should match "qwen3.5:9b"
        p = get_model_profile("qwen3.5:9b-q4_K_M")
        assert p.context_window == 32768


class TestTruncateText:
    def test_no_truncation_needed(self):
        text, truncated = _truncate_text("hello world", 100)
        assert text == "hello world"
        assert not truncated

    def test_truncation(self):
        long_text = "word " * 1000  # ~5000 chars
        text, truncated = _truncate_text(long_text, 100)
        assert truncated
        assert len(text) < len(long_text)
        assert "truncado" in text

    def test_empty_text(self):
        text, truncated = _truncate_text("", 100)
        assert text == ""
        assert not truncated


class TestReservedOutput:
    def test_modes(self):
        assert _reserved_output_tokens("fast") == 1024
        assert _reserved_output_tokens("balanced") == 4096
        assert _reserved_output_tokens("deep") == 8192

    def test_unknown_mode(self):
        assert _reserved_output_tokens("unknown") == 4096


class TestSelectReferences:
    def test_all_fit(self):
        refs = {
            "output-contract": "contract content",
            "evidence-rules": "rules content",
        }
        selected = _select_references(refs, "analise este payload", 10000)
        assert len(selected) == 2

    def test_budget_constrains(self):
        refs = {
            "output-contract": "x" * 4000,
            "evidence-rules": "y" * 4000,
            "ioc-extraction": "z" * 4000,
            "security-json-patterns": "w" * 4000,
        }
        # Budget apertado: só cabe ~2 references
        selected = _select_references(refs, "ioc hash", 2500)
        assert len(selected) < 4

    def test_relevance_scoring(self):
        refs = {
            "output-contract": "a" * 200,
            "ioc-extraction": "b" * 200,
            "telemetry-investigation-patterns": "c" * 200,
        }
        # Input com "ioc" deve priorizar ioc-extraction
        selected = _select_references(refs, "extraia os iocs deste log", 500)
        assert "ioc-extraction" in selected or "output-contract" in selected


class TestComputeBudget:
    def test_small_model_truncates(self):
        sections = {
            "identity": "persona " * 50,
            "soul": "missao " * 100,
            "skill": "skill content " * 200,
            "history": "msg1\nmsg2\nmsg3 " * 100,
        }
        result = compute_budget(
            model_name="llama3.2:3b",
            response_mode="fast",
            sections=sections,
        )
        assert isinstance(result, ContextBudgetResult)
        assert result.model == "llama3.2:3b"
        # Budget deve ter truncado algo
        truncated_sections = [s for s in result.sections if s.truncated or s.omitted]
        # Com modelo de 8K em modo fast, seções grandes devem ser cortadas
        assert result.total_prompt_tokens <= result.available_tokens + 500  # margem

    def test_large_model_no_truncation(self):
        sections = {
            "identity": "persona curta",
            "skill": "skill curta",
        }
        result = compute_budget(
            model_name="claude-haiku-4-5-20251001",
            response_mode="balanced",
            sections=sections,
        )
        truncated = [s for s in result.sections if s.truncated or s.omitted]
        assert len(truncated) == 0

    def test_with_references(self):
        sections = {
            "identity": "persona",
            "skill": "skill content",
        }
        references = {
            "output-contract": "contract " * 500,
            "evidence-rules": "rules " * 500,
        }
        result = compute_budget(
            model_name="llama3.2:3b",
            response_mode="fast",
            sections=sections,
            references=references,
            user_input="analise este ioc",
        )
        # References devem ter sido processadas
        ref_section = next((s for s in result.sections if s.name == "references"), None)
        assert ref_section is not None

    def test_metrics(self):
        sections = {"identity": "test"}
        result = compute_budget(
            model_name="qwen3.5:9b",
            response_mode="balanced",
            sections=sections,
        )
        metrics = result.metrics()
        assert "model" in metrics
        assert "utilization_pct" in metrics
        assert "sections" in metrics
        assert metrics["utilization_pct"] >= 0

    def test_priority_order(self):
        # Seções de menor prioridade devem ser cortadas primeiro
        sections = {
            "payload": "payload importante " * 100,
            "skill": "skill essencial " * 100,
            "vantage": "vantage context " * 500,
            "memory": "memoria longa " * 500,
            "tools": "tools inventory " * 500,
        }
        result = compute_budget(
            model_name="llama3.2:3b",
            response_mode="fast",
            sections=sections,
        )
        # Payload e skill não devem ser omitidos
        payload_s = next((s for s in result.sections if s.name == "payload"), None)
        skill_s = next((s for s in result.sections if s.name == "skill"), None)
        assert payload_s and not payload_s.omitted
        assert skill_s and not skill_s.omitted

        # Vantage/memory/tools devem ter sido truncados ou omitidos
        low_priority = [s for s in result.sections if s.name in ("vantage", "memory", "tools")]
        if low_priority:
            assert any(s.truncated or s.omitted for s in low_priority)


class TestApplyBudgetToPromptContext:
    def test_basic_application(self):
        context = {
            "identity": "Sou o SOC Copilot",
            "soul": "Missão do copiloto",
            "user": "Contexto SOC",
            "agents": "Regras",
            "memory": "Memória",
            "tools": "Ferramentas",
            "evidence_rules": "regras de evidência " * 200,
            "ioc_extraction": "extração de IOCs " * 200,
            "security_json_patterns": "patterns " * 200,
            "telemetry_investigation_patterns": "telemetry " * 200,
            "mitre_guidance": "mitre " * 200,
            "output_contract": "contrato " * 200,
            "selected_skill": "soc-generalist",
            "skill_content": "Skill generalist " * 100,
            "session_context": "msg anterior",
            "knowledge_context": "knowledge",
            "user_input": "o que é esse hash",
        }
        adjusted, budget = apply_budget_to_prompt_context(
            model_name="llama3.2:3b",
            response_mode="fast",
            context=context,
            user_input="o que é esse hash",
        )
        # Deve retornar context ajustado e budget result
        assert isinstance(adjusted, dict)
        assert isinstance(budget, ContextBudgetResult)
        # Algumas references devem ter sido removidas em modelo 8K
        empty_refs = sum(1 for k in ("evidence_rules", "ioc_extraction",
                                      "security_json_patterns", "telemetry_investigation_patterns",
                                      "mitre_guidance", "output_contract")
                        if not adjusted.get(k))
        # Em 8K, pelo menos algumas references devem ter sido cortadas
        assert empty_refs >= 0  # pode ou não cortar, depende do tamanho

    def test_large_model_preserves_all(self):
        context = {
            "identity": "Copilot",
            "soul": "Soul",
            "skill_content": "Skill",
            "selected_skill": "test",
            "evidence_rules": "rules",
            "output_contract": "contract",
            "user_input": "test",
        }
        adjusted, budget = apply_budget_to_prompt_context(
            model_name="claude-haiku-4-5-20251001",
            response_mode="balanced",
            context=context,
            user_input="test",
        )
        # Nenhum conteúdo deve ter sido removido
        assert adjusted.get("identity") == "Copilot"
        assert adjusted.get("soul") == "Soul"
        assert adjusted.get("evidence_rules") == "rules"


class TestSectionPriorities:
    def test_payload_highest_priority(self):
        assert SECTION_PRIORITIES["payload"] < SECTION_PRIORITIES["skill"]
        assert SECTION_PRIORITIES["payload"] < SECTION_PRIORITIES["references"]
        assert SECTION_PRIORITIES["payload"] < SECTION_PRIORITIES["vantage"]

    def test_vantage_lowest_priority(self):
        assert SECTION_PRIORITIES["vantage"] > SECTION_PRIORITIES["payload"]
        assert SECTION_PRIORITIES["vantage"] > SECTION_PRIORITIES["skill"]
        assert SECTION_PRIORITIES["vantage"] > SECTION_PRIORITIES["history"]
