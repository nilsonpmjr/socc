"""
Valida higiene basica dos templates HTML para evitar regressao de estilos e handlers inline.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
TEMPLATES = [
    ROOT / "soc_copilot" / "templates" / "chat.html",
    ROOT / "soc_copilot" / "templates" / "index.html",
]

INLINE_STYLE = re.compile(r'style="', re.IGNORECASE)
INLINE_HANDLER = re.compile(r"\bon[a-z]+\s*=", re.IGNORECASE)
SCRIPT_BLOCK = re.compile(r"<script[\s\S]*?</script>", re.IGNORECASE)

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    resultados.append((PASS if condicao else FAIL, nome, detalhe))


for template in TEMPLATES:
    text = template.read_text(encoding="utf-8")
    markup = SCRIPT_BLOCK.sub("", text)
    check(
        f"{template.name}_no_inline_style",
        INLINE_STYLE.search(markup) is None,
        "style= encontrado" if INLINE_STYLE.search(markup) else "",
    )
    check(
        f"{template.name}_no_inline_handler",
        INLINE_HANDLER.search(markup) is None,
        "on*= encontrado" if INLINE_HANDLER.search(markup) else "",
    )


print(f"\n{'='*60}")
print(f"SOCC Templates — Hygiene  ({len(resultados)} checks)")
print("=" * 60)
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
