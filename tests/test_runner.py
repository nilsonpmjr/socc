"""
test_runner.py
Fase 11 — Testes de regressão do SOC Copilot MVP.
Executa o pipeline completo (sem HTTP) contra dataset_mvp.json
e valida estrutura de saída, campos extraídos e conformidade textual.
"""
from __future__ import annotations

import json
import sys
import time
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

# ---------------------------------------------------------------------------
# Helpers de asserção
# ---------------------------------------------------------------------------
MARKDOWN_BANIDO = ("**", "__", "```", "# ")
CHAVES_ANALYSIS = {
    "resumo_factual", "hipoteses", "lacunas",
    "classificacao_sugerida", "mitre_candidato",
    "modelo_sugerido", "blocos_recomendados",
    "proximos_passos", "alertas_de_qualidade",
}
CHAVES_CLS_SUGERIDA = {"tipo", "confianca", "racional"}


def _check_no_markdown(draft: str) -> list[str]:
    return [m for m in MARKDOWN_BANIDO if m in draft]


def _check_analysis_schema(analysis: dict) -> list[str]:
    erros = []
    faltantes = CHAVES_ANALYSIS - set(analysis.keys())
    if faltantes:
        erros.append(f"Chaves ausentes em analysis: {faltantes}")
    cls = analysis.get("classificacao_sugerida", {})
    if not isinstance(cls, dict):
        erros.append("classificacao_sugerida não é dict")
    elif "racional" not in cls and "justificativa" in cls:
        erros.append("classificacao_sugerida usa 'justificativa' em vez de 'racional'")
    if not isinstance(analysis.get("hipoteses"), list):
        erros.append("hipoteses não é lista")
    if not isinstance(analysis.get("lacunas"), list):
        erros.append("lacunas não é lista")
    return erros


def _check_draft_blocks(classificacao: str, draft: str, is_icatu: bool = False) -> list[str]:
    erros = []
    cls = classificacao.upper()

    if cls == "TP":
        # Template TP (padrão e Icatu) tem Análise Técnica e Recomendação
        for bloco in ("Análise Técnica:", "Recomendação:"):
            if bloco not in draft:
                erros.append(f"Bloco obrigatório ausente no draft TP: '{bloco}'")
    elif is_icatu and cls != "TP":
        # Template Icatu repasse usa "Encaminhamento:" em vez de "Classificação Final:"
        if "Encaminhamento:" not in draft:
            erros.append(f"'Encaminhamento:' ausente no draft Icatu {cls}")
    elif cls in {"BTP", "FP", "TN", "LTF"}:
        if "Classificação Final:" not in draft:
            erros.append(f"'Classificação Final:' ausente no draft {cls}")
    return erros


def _check_acentuacao(draft: str) -> list[str]:
    acentuados = "áéíóúãõçÁÉÍÓÚÃÕÇ"
    if not any(c in draft for c in acentuados):
        return ["Nenhum caractere acentuado detectado — possível corrupção de encoding"]
    return []


# ---------------------------------------------------------------------------
# Execução principal
# ---------------------------------------------------------------------------
def run_tests(dataset_path: Path) -> None:
    with open(dataset_path, encoding="utf-8") as f:
        casos = json.load(f)

    total = len(casos)
    falhas: dict[str, list[str]] = {}

    for caso in casos:
        tc_id = caso["id"]
        erros: list[str] = []

        t0 = time.perf_counter()
        try:
            # 1. Input Adapter
            fmt, campos, raw_original = input_adapter.adapt(caso["payload"])

            # 2. Parser Engine
            fields = parser_engine.parse(campos, raw_original)

            # 3. Rule Loader
            pack = rule_loader.load(regra=caso.get("regra", ""), cliente=caso.get("cliente", ""))

            # 4. Semi-LLM (sem TI real — passa dict vazio)
            analysis = semi_llm_adapter.run(
                fields=fields,
                ti_results={},
                raw_text=raw_original,
                regra=caso.get("regra", ""),
                cliente=caso.get("cliente", ""),
                pack=pack,
            )

            # 5. Draft Engine
            classificacao = caso.get("classificacao", "TP")
            draft, template = draft_engine.generate(
                classificacao=classificacao,
                fields=fields,
                ti_results={},
                pack=pack,
                analysis=analysis,
            )

        except Exception as exc:
            erros.append(f"EXCEÇÃO não tratada: {type(exc).__name__}: {exc}")
            falhas[tc_id] = erros
            continue

        elapsed = time.perf_counter() - t0

        # Validações
        erros += _check_analysis_schema(analysis)
        erros += _check_no_markdown(draft)
        erros += _check_draft_blocks(classificacao, draft, is_icatu=pack.is_icatu)
        erros += _check_acentuacao(draft)

        if elapsed > 2.0:
            erros.append(f"Performance: pipeline demorou {elapsed:.2f}s (limite: 2s)")

        if erros:
            falhas[tc_id] = erros

    # Relatório
    print(f"\n{'='*60}")
    print(f"SOC Copilot — Regressão MVP  ({total} casos)")
    print(f"{'='*60}")
    aprovados = total - len(falhas)
    print(f"  Aprovados : {aprovados}/{total}")
    print(f"  Falhas    : {len(falhas)}/{total}")
    print()

    for tc_id, erros in falhas.items():
        print(f"  FALHA [{tc_id}]")
        for e in erros:
            print(f"    - {e}")
        print()

    if not falhas:
        print("  Todos os casos passaram.\n")

    return falhas


if __name__ == "__main__":
    dataset = Path(__file__).parent / "dataset_mvp.json"
    falhas = run_tests(dataset)
    sys.exit(1 if falhas else 0)
