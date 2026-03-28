"""
Valida bootstrap do runtime local inspirado em workspace autocontido.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from soc_copilot.modules.soc_copilot_loader import load_soc_copilot
from socc.cli.installer import (
    bootstrap_runtime,
    runtime_agent_home,
    runtime_bin_dir,
    runtime_checkout_link,
    runtime_home,
    runtime_project_link,
)

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


tmpdir = tempfile.TemporaryDirectory()
runtime_root = Path(tmpdir.name) / ".socc-test"
original_agent_home = os.environ.get("SOCC_AGENT_HOME")
original_socc_home = os.environ.get("SOCC_HOME")


try:
    result = bootstrap_runtime(runtime_root, force=True)
    agent_home = runtime_agent_home(runtime_root)
    manifest_path = runtime_root / "socc.json"

    check("bootstrap_runtime_dir_exists", runtime_root.exists(), str(runtime_root))
    check("bootstrap_agent_home_exists", agent_home.exists(), str(agent_home))
    check("bootstrap_manifest_exists", manifest_path.exists(), str(manifest_path))
    check("bootstrap_workspace_seeded", (agent_home / "SOUL.md").exists())
    check("bootstrap_workspace_has_references", (agent_home / "references" / "evidence-rules.md").exists())
    check("bootstrap_workspace_has_rag_policy", (agent_home / "references" / "knowledge-ingestion-policy.md").exists())
    check("bootstrap_intel_registry_exists", (runtime_root / "intel" / "sources.json").exists())
    check("bootstrap_launcher_exists", (runtime_bin_dir(runtime_root) / "socc").exists())
    check("bootstrap_checkout_link_exists", runtime_checkout_link(runtime_root).exists())
    check("bootstrap_project_link_exists", runtime_project_link(runtime_root).exists())

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    check(
        "bootstrap_manifest_paths",
        manifest.get("paths", {}).get("agent_home") == str(agent_home),
    )
    check(
        "bootstrap_manifest_features",
        manifest.get("features", {}).get("chat_streaming_env") == "SOCC_FEATURE_CHAT_STREAMING",
    )
    check("bootstrap_manifest_intel_path", manifest.get("paths", {}).get("intel_home") == str(runtime_root / "intel"))
    check("bootstrap_manifest_launcher", manifest.get("paths", {}).get("cli_launcher") == str(runtime_root / "bin" / "socc"))
    check("bootstrap_manifest_checkout_link", manifest.get("paths", {}).get("checkout_link") == str(runtime_checkout_link(runtime_root)))
    check("bootstrap_manifest_project_link", manifest.get("paths", {}).get("project_link") == str(runtime_project_link(runtime_root)))
    check("bootstrap_manifest_service_pid", manifest.get("paths", {}).get("service_pid") == str(runtime_root / "logs" / "socc-serve.pid"))
    check("bootstrap_manifest_rag_env", manifest.get("rag", {}).get("chunk_chars_env") == "SOCC_RAG_CHUNK_CHARS")
    check("bootstrap_result_agent_home", result.get("agent_home") == str(agent_home))
    check("bootstrap_result_project_linked", result.get("project_linked") in {"yes", "no"})

    os.environ["SOCC_AGENT_HOME"] = str(agent_home)
    config = load_soc_copilot()
    check("bootstrap_loader_uses_runtime_workspace", config.base_path == agent_home, str(config.base_path))
    check("bootstrap_loader_has_skill", "payload-triage" in config.skills)

    os.environ["SOCC_HOME"] = str(runtime_root)
    check("bootstrap_runtime_home_env", runtime_home() == runtime_root, str(runtime_home()))
except Exception as exc:
    check("runtime_bootstrap_flow", False, str(exc))
finally:
    if original_agent_home is None:
        os.environ.pop("SOCC_AGENT_HOME", None)
    else:
        os.environ["SOCC_AGENT_HOME"] = original_agent_home
    if original_socc_home is None:
        os.environ.pop("SOCC_HOME", None)
    else:
        os.environ["SOCC_HOME"] = original_socc_home


print(f"\n{'='*60}")
print(f"SOCC Runtime — Bootstrap  ({len(resultados)} checks)")
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

tmpdir.cleanup()
sys.exit(1 if falhas else 0)
