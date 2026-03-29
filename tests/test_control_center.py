"""
Valida painel de controle do runtime e troca manual de agente.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from socc.cli.installer import bootstrap_runtime, runtime_agent_home
from socc.cli import oauth_flow as oauth_flow_module
from socc.core import engine as engine_module
from socc.core.engine import (
    control_center_summary_payload,
    oauth_login_provider_payload,
    oauth_logout_provider_payload,
    select_active_agent_payload,
    select_runtime_model_payload,
    select_vantage_modules_payload,
    warmup_runtime_model_payload,
)
from socc.gateway import vantage_api as vantage_gateway

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


tmpdir = tempfile.TemporaryDirectory()
runtime_root = Path(tmpdir.name) / ".socc-test"
original_socc_home = os.environ.get("SOCC_HOME")
original_agent_home = os.environ.get("SOCC_AGENT_HOME")
original_list_backend_models = engine_module.list_backend_models
original_warmup_backend_model = engine_module.warmup_backend_model
original_vantage_status = vantage_gateway.status_payload
original_oauth_login = oauth_flow_module.oauth_login
original_load_credentials = oauth_flow_module.load_credentials
original_credentials_valid = oauth_flow_module.credentials_valid
original_clear_credentials = oauth_flow_module.clear_credentials

try:
    engine_module.list_backend_models = lambda timeout=2.0: {
        "backend": "ollama",
        "provider": "ollama",
        "endpoint": "http://127.0.0.1:11434",
        "reachable": True,
        "models": [{"name": "llama3.2:3b"}, {"name": "qwen3.5:9b"}, {"name": "gemma3:4b"}],
        "error": "",
    }
    engine_module.warmup_backend_model = lambda **kwargs: {
        "backend": "ollama",
        "provider": "ollama",
        "endpoint": "http://127.0.0.1:11434",
        "model": kwargs.get("model", ""),
        "warmed": True,
        "error": "",
    }
    vantage_gateway.status_payload = lambda: {
        "enabled": True,
        "configured": True,
        "base_url": "https://vantage.local",
        "auth_mode": "bearer",
        "selected_modules": ["feed", "hunting"],
        "modules": [
            {"id": "feed", "label": "Feed", "path": "/api/feed", "selected": True, "capabilities": ["intel_feed"]},
            {"id": "hunting", "label": "Hunting", "path": "/api/hunting", "selected": True, "capabilities": ["hunt_cases"]},
        ],
    }
    oauth_state = {
        "anthropic": {},
        "openai": {},
    }
    def _fake_oauth_login(provider_name: str, force_reauth: bool = False) -> dict[str, object]:
        oauth_state[provider_name] = {
            "access_token": f"{provider_name}-token",
            "refresh_token": f"{provider_name}-refresh",
            "expires_at": 4102444800,
            "saved_at": 1700000000,
        }
        return {
            "provider": provider_name,
            "access_token": f"{provider_name}-token",
            "refresh_token": f"{provider_name}-refresh",
            "expires_in": 3600,
        }

    oauth_flow_module.oauth_login = _fake_oauth_login
    oauth_flow_module.load_credentials = lambda provider_name: dict(oauth_state.get(provider_name) or {})
    oauth_flow_module.credentials_valid = lambda provider_name: bool((oauth_state.get(provider_name) or {}).get("access_token"))
    oauth_flow_module.clear_credentials = lambda provider_name: oauth_state.__setitem__(provider_name, {}) is None or True
    bootstrap_runtime(runtime_root, force=True)
    primary_agent = runtime_agent_home(runtime_root)
    secondary_agent = runtime_root / "workspace" / "soc-reviewer"
    if secondary_agent.exists():
        shutil.rmtree(secondary_agent)
    shutil.copytree(primary_agent, secondary_agent)

    os.environ["SOCC_HOME"] = str(runtime_root)
    os.environ.pop("SOCC_AGENT_HOME", None)

    summary = control_center_summary_payload(limit_sessions=5)
    agents = ((summary.get("agents") or {}).get("available") or [])
    selected = (summary.get("agents") or {}).get("selected") or {}
    check("control_center_has_agents", len(agents) >= 2, str(agents))
    check("control_center_selected_agent", bool(selected.get("path")), str(selected))
    check("control_center_has_runtime", "runtime" in summary and "service" in summary)
    check("control_center_has_diagnostics", "diagnostics" in summary and "checks" in summary["diagnostics"])
    check("control_center_has_runtime_models", bool(((summary.get("runtime_models") or {}).get("catalog") or {}).get("models")))
    check("control_center_has_vantage", bool((summary.get("vantage") or {}).get("modules")))
    check("control_center_has_oauth", len((summary.get("oauth") or {}).get("providers") or []) == 2)

    switched = select_active_agent_payload("soc-reviewer", home=runtime_root)
    new_selected = (switched.get("selected_agent") or {}).get("path") or ""
    env_file = runtime_root / ".env"
    env_text = env_file.read_text(encoding="utf-8")

    check("control_center_switches_agent_env", os.environ.get("SOCC_AGENT_HOME", "").endswith("soc-reviewer"))
    check("control_center_switches_agent_payload", str(new_selected).endswith("soc-reviewer"))
    check("control_center_persists_agent_env", "SOCC_AGENT_HOME=" in env_text and "soc-reviewer" in env_text)

    model_selected = select_runtime_model_payload(
        response_mode="fast",
        model="gemma3:4b",
        home=runtime_root,
    )
    env_text = env_file.read_text(encoding="utf-8")
    check("control_center_select_model_payload", model_selected.get("model") == "gemma3:4b")
    check("control_center_select_model_env", "SOCC_OLLAMA_FAST_MODEL=gemma3:4b" in env_text)

    warmed = warmup_runtime_model_payload(response_mode="fast")
    check("control_center_warmup_model", ((warmed.get("result") or {}).get("warmed")) is True)
    check("control_center_warmup_keeps_model", ((warmed.get("result") or {}).get("model")) == "gemma3:4b")

    vantage_selected = select_vantage_modules_payload(
        module_ids=["feed", "watchlist"],
        enabled=True,
        home=runtime_root,
    )
    env_text = env_file.read_text(encoding="utf-8")
    check("control_center_vantage_modules_payload", vantage_selected.get("selected_modules") == ["feed", "watchlist"], str(vantage_selected))
    check("control_center_vantage_modules_env", "SOCC_VANTAGE_ENABLED_MODULES=feed,watchlist" in env_text, env_text)
    check("control_center_vantage_enabled_env", "SOCC_VANTAGE_ENABLED=true" in env_text, env_text)

    oauth_connected = oauth_login_provider_payload("anthropic", home=runtime_root)
    env_text = env_file.read_text(encoding="utf-8")
    check("control_center_oauth_login_provider", ((oauth_connected.get("oauth") or {}).get("configured")) is True, str(oauth_connected))
    check("control_center_oauth_login_env", "SOCC_AUTH_METHOD_ANTHROPIC=oauth" in env_text, env_text)
    check("control_center_oauth_login_llm_enabled", "LLM_ENABLED=true" in env_text, env_text)

    oauth_disconnected = oauth_logout_provider_payload("anthropic", home=runtime_root)
    env_text = env_file.read_text(encoding="utf-8")
    check("control_center_oauth_logout_provider", ((oauth_disconnected.get("oauth") or {}).get("configured")) is False, str(oauth_disconnected))
    active_lines = [line.strip() for line in env_text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    check("control_center_oauth_logout_env", "SOCC_AUTH_METHOD_ANTHROPIC=oauth" not in active_lines, env_text)
except Exception as exc:
    check("control_center_flow", False, str(exc))
finally:
    engine_module.list_backend_models = original_list_backend_models
    engine_module.warmup_backend_model = original_warmup_backend_model
    vantage_gateway.status_payload = original_vantage_status
    oauth_flow_module.oauth_login = original_oauth_login
    oauth_flow_module.load_credentials = original_load_credentials
    oauth_flow_module.credentials_valid = original_credentials_valid
    oauth_flow_module.clear_credentials = original_clear_credentials
    if original_socc_home is None:
        os.environ.pop("SOCC_HOME", None)
    else:
        os.environ["SOCC_HOME"] = original_socc_home
    if original_agent_home is None:
        os.environ.pop("SOCC_AGENT_HOME", None)
    else:
        os.environ["SOCC_AGENT_HOME"] = original_agent_home
    tmpdir.cleanup()


print(f"\n{'='*60}")
print(f"SOCC Runtime — Control Center  ({len(resultados)} checks)")
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
