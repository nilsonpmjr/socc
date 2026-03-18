"""
test_edge_cases.py
Fase 11 — Validação de casos extremos: semi-LLM, parser e draft engine.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from soc_copilot.modules import (
    draft_engine,
    input_adapter,
    parser_engine,
    rule_loader,
    semi_llm_adapter,
)

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


def pipeline(payload: str, classificacao: str = "TP", cliente: str = "Padrão", regra: str = "test"):
    fmt, campos, raw = input_adapter.adapt(payload)
    fields = parser_engine.parse(campos, raw)
    pack = rule_loader.load(regra=regra, cliente=cliente)
    analysis = semi_llm_adapter.run(
        fields=fields, ti_results={}, raw_text=raw,
        regra=regra, cliente=cliente, pack=pack,
    )
    draft, template = draft_engine.generate(
        classificacao=classificacao, fields=fields,
        ti_results={}, pack=pack, analysis=analysis,
    )
    return fields, analysis, draft, template


# ---------------------------------------------------------------------------
# 1. Payload vazio
# ---------------------------------------------------------------------------
try:
    fmt, campos, raw = input_adapter.adapt("   ")
    fields = parser_engine.parse(campos, raw)
    pack = rule_loader.load(regra="", cliente="Padrão")
    analysis = semi_llm_adapter.run(fields=fields, ti_results={}, raw_text=raw,
                                     regra="", cliente="Padrão", pack=pack)
    check("payload_vazio_nao_explode", True)
    check("payload_vazio_analysis_schema_completo",
          set(analysis.keys()) >= {"hipoteses", "lacunas", "classificacao_sugerida"})
    draft, _ = draft_engine.generate("TP", fields, {}, pack, analysis)
    check("payload_vazio_draft_nao_vazio", bool(draft.strip()))
except Exception as e:
    check("payload_vazio_nao_explode", False, str(e))

# ---------------------------------------------------------------------------
# 2. Payload apenas com espaços e quebras de linha
# ---------------------------------------------------------------------------
try:
    _, analysis, draft, _ = pipeline("\n\n\t\n\n")
    check("payload_whitespace_nao_explode", True)
    check("payload_whitespace_draft_nao_vazio", bool(draft.strip()))
except Exception as e:
    check("payload_whitespace_nao_explode", False, str(e))

# ---------------------------------------------------------------------------
# 3. Payload Unicode agressivo (emojis, RTL, caracteres especiais)
# ---------------------------------------------------------------------------
try:
    payload_unicode = '{"usuario": "joão.silva", "ip": "10.0.0.1", "ação": "login \u202e\u0041\u004c\u0045\u0052\u0054\u202c", "emoji": "\U0001f4a3\u26a0\ufe0f"}'
    fields, analysis, draft, _ = pipeline(payload_unicode)
    check("unicode_nao_explode", True)
    check("unicode_draft_sem_crash", bool(draft))
    check("unicode_sem_markdown", not any(m in draft for m in ("**", "```")))
except Exception as e:
    check("unicode_nao_explode", False, str(e))

# ---------------------------------------------------------------------------
# 4. JSON com campos nulos e listas vazias
# ---------------------------------------------------------------------------
try:
    payload_nulos = '{"usuario": null, "ip": null, "horario": null, "destino": "", "iocs": []}'
    fields, analysis, draft, _ = pipeline(payload_nulos)
    check("json_nulos_nao_explode", True)
    check("json_nulos_campos_na", fields.get("Usuario") == "N/A" or fields.get("IP_Origem") == "N/A")
except Exception as e:
    check("json_nulos_nao_explode", False, str(e))

# ---------------------------------------------------------------------------
# 5. Semi-LLM: análise sem nenhum sinal (retorna "indefinido")
# ---------------------------------------------------------------------------
try:
    fields_sem_sinal = {
        "Horario": "N/A", "Usuario": "N/A", "IP_Origem": "N/A",
        "IP_Origem_Privado": True, "Destino": "N/A", "Caminho": "N/A",
        "LogSource": "N/A", "Assunto": "N/A",
        "IOCs": {"ips_externos": [], "ips_internos": [], "urls": [], "dominios": [], "hashes": []},
    }
    pack = rule_loader.load(regra="", cliente="Padrão")
    analysis = semi_llm_adapter.run(fields=fields_sem_sinal, ti_results={},
                                     raw_text="", regra="", cliente="Padrão", pack=pack)
    cls = analysis["classificacao_sugerida"]
    check("sem_sinais_classificacao_indefinido", cls.get("tipo") == "indefinido")
    check("sem_sinais_hipoteses_vazia", analysis["hipoteses"] == [])
    check("sem_sinais_racional_presente", "racional" in cls)
except Exception as e:
    check("sem_sinais_nao_explode", False, str(e))

# ---------------------------------------------------------------------------
# 6. Semi-LLM: classificacao_sugerida nunca expõe 'justificativa' (bug Fase 7)
# ---------------------------------------------------------------------------
try:
    payload_tp = '{"src_ip": "203.0.113.5", "action": "blocked"}'
    fields, analysis, draft, _ = pipeline(payload_tp)
    cls = analysis["classificacao_sugerida"]
    check("cls_sugerida_sem_justificativa", "justificativa" not in cls)
    check("cls_sugerida_com_racional", "racional" in cls)
except Exception as e:
    check("cls_sugerida_schema_nao_explode", False, str(e))

# ---------------------------------------------------------------------------
# 7. Draft Engine: classificação desconhecida não explode
# ---------------------------------------------------------------------------
try:
    fields, analysis, draft, template = pipeline('{"ip": "1.2.3.4"}', classificacao="XPTO")
    check("cls_desconhecida_nao_explode", True)
    check("cls_desconhecida_template_nao_mapeado", template == "nao_mapeado")
    check("cls_desconhecida_draft_nao_vazio", bool(draft.strip()))
except Exception as e:
    check("cls_desconhecida_nao_explode", False, str(e))

# ---------------------------------------------------------------------------
# 8. Payload gigante (10 KB de lixo) — performance e robustez
# ---------------------------------------------------------------------------
import time
try:
    payload_grande = "A" * 5000 + " ip=10.0.0.1 usuario=fulano " + "B" * 5000
    t0 = time.perf_counter()
    fields, analysis, draft, _ = pipeline(payload_grande)
    elapsed = time.perf_counter() - t0
    check("payload_grande_nao_explode", True)
    check("payload_grande_dentro_do_limite", elapsed < 3.0, f"{elapsed:.2f}s")
except Exception as e:
    check("payload_grande_nao_explode", False, str(e))

# ---------------------------------------------------------------------------
# 9. Icatu TP usa template TP padrão (não repasse)
# ---------------------------------------------------------------------------
try:
    fields, analysis, draft, template = pipeline(
        '{"src_ip": "203.0.113.5", "action": "exploit"}',
        classificacao="TP", cliente="Icatu",
    )
    check("icatu_tp_usa_template_tp", "icatu_repasse" not in template)
    check("icatu_tp_tem_recomendacao", "Recomendação:" in draft)
except Exception as e:
    check("icatu_tp_nao_explode", False, str(e))

# ---------------------------------------------------------------------------
# 10. _validate_output rejeita chave extra (anti-injeção de texto livre)
# ---------------------------------------------------------------------------
from soc_copilot.modules.semi_llm_adapter import _validate_output
saida_injetada = {
    "resumo_factual": {}, "hipoteses": [], "lacunas": [],
    "classificacao_sugerida": {}, "mitre_candidato": {},
    "modelo_sugerido": "", "blocos_recomendados": {},
    "proximos_passos": [], "alertas_de_qualidade": [],
    "INJECAO": "texto livre gerado pela LLM",
}
validated = _validate_output(saida_injetada)
check("anti_injecao_chave_extra_bloqueada", "INJECAO" not in validated)

# ---------------------------------------------------------------------------
# Relatório
# ---------------------------------------------------------------------------
print(f"\n{'='*60}")
print(f"SOC Copilot — Casos Extremos  ({len(resultados)} checks)")
print("="*60)
falhas = [(n, d) for s, n, d in resultados if s == FAIL]
aprovados = len(resultados) - len(falhas)
print(f"  Aprovados : {aprovados}/{len(resultados)}")
print(f"  Falhas    : {len(falhas)}/{len(resultados)}")
print()
for nome, detalhe in falhas:
    extra = f" — {detalhe}" if detalhe else ""
    print(f"  FALHA: {nome}{extra}")
if not falhas:
    print("  Todos os checks passaram.")
print()

sys.exit(1 if falhas else 0)
