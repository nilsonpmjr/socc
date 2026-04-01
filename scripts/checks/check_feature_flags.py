"""
Valida resolução de feature flags e payload exposto ao runtime.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from socc.utils.feature_flags import FEATURE_FLAG_ENVS, feature_flags_payload, resolve_feature_flags

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


original_env = {name: os.environ.get(name) for name in FEATURE_FLAG_ENVS.values()}

try:
    for name in FEATURE_FLAG_ENVS.values():
        os.environ.pop(name, None)

    defaults = resolve_feature_flags()
    payload = feature_flags_payload()
    check("feature_flags_default_chat", defaults.chat_api is True)
    check("feature_flags_default_streaming", defaults.chat_streaming is True)
    check("feature_flags_payload_keys", set(payload.keys()) == set(FEATURE_FLAG_ENVS.keys()))

    os.environ[FEATURE_FLAG_ENVS["chat_streaming"]] = "false"
    os.environ[FEATURE_FLAG_ENVS["threat_intel"]] = "0"
    os.environ[FEATURE_FLAG_ENVS["runtime_api"]] = "no"
    overridden = resolve_feature_flags()

    check("feature_flags_override_streaming", overridden.chat_streaming is False)
    check("feature_flags_override_ti", overridden.threat_intel is False)
    check("feature_flags_override_runtime", overridden.runtime_api is False)
except Exception as exc:
    check("feature_flags_flow", False, str(exc))
finally:
    for name, value in original_env.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


print(f"\n{'='*60}")
print(f"SOCC Runtime — Feature Flags  ({len(resultados)} checks)")
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
