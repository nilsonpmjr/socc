"""
Valida reautenticacao OAuth e transporte OpenAI/Codex do runtime.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import socc.cli.oauth_flow as oauth_flow

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


tmpdir = tempfile.TemporaryDirectory()
original_credentials_dir = oauth_flow._credentials_dir
original_wait_for_callback = oauth_flow._wait_for_callback
original_exchange_code = oauth_flow._exchange_code
original_webbrowser_open = oauth_flow.webbrowser.open

try:
    oauth_flow._credentials_dir = lambda: Path(tmpdir.name)

    saved = oauth_flow.save_credentials(
        "openai",
        {
            "access_token": "cached-token",
            "refresh_token": "cached-refresh",
            "expires_in": 3600,
        },
    )
    check("oauth_test_saved_credentials", saved.exists(), str(saved))

    reused = oauth_flow.oauth_login("openai")
    check("oauth_test_reuse_existing", reused.get("reused") is True, str(reused))
    check("oauth_test_reuse_token", reused.get("access_token") == "cached-token", str(reused))

    oauth_flow.webbrowser.open = lambda _url: True
    oauth_flow._wait_for_callback = lambda *args, **kwargs: ("auth-code", None, None)
    oauth_flow._exchange_code = lambda provider, code, verifier, redirect_uri: {
        "access_token": "fresh-token",
        "refresh_token": "fresh-refresh",
        "expires_in": 3600,
    }

    forced = oauth_flow.oauth_login("openai", force_reauth=True)
    check("oauth_test_force_reauth_not_reused", forced.get("reused") is not True, str(forced))
    check("oauth_test_force_reauth_new_token", forced.get("access_token") == "fresh-token", str(forced))
    reloaded = oauth_flow.load_credentials("openai") or {}
    check("oauth_test_force_reauth_persisted", reloaded.get("access_token") == "fresh-token", str(reloaded))
except Exception as exc:
    check("oauth_test_flow", False, str(exc))
finally:
    oauth_flow._credentials_dir = original_credentials_dir
    oauth_flow._wait_for_callback = original_wait_for_callback
    oauth_flow._exchange_code = original_exchange_code
    oauth_flow.webbrowser.open = original_webbrowser_open
    tmpdir.cleanup()


print(f"\n{'='*60}")
print(f"SOCC Runtime — OAuth Flow  ({len(resultados)} checks)")
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
