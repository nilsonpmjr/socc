"""
Valida as fachadas de migracao gradual de `soc_copilot` para `socc`.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from soc_copilot.modules import persistence as legacy_persistence
from socc.core import agent_loader, analysis, chat, input_adapter, parser, storage
from socc.core.engine import prepare_payload_input
from socc.gateway import threat_intel

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


tmpdir = tempfile.TemporaryDirectory()
db_path = str(Path(tmpdir.name) / "migration.sqlite3")
original_db_path = legacy_persistence.DB_PATH

try:
    legacy_persistence.DB_PATH = db_path
    storage.init_db()

    adapted_fmt, adapted_fields, adapted_raw = input_adapter.adapt("srcip=10.0.0.5 dstip=8.8.8.8 action=blocked")
    parsed = parser.parse_payload("srcip=10.0.0.5 dstip=8.8.8.8 action=blocked")
    prepared = prepare_payload_input("srcip=10.0.0.5 dstip=8.8.8.8 action=blocked")
    pack = analysis.load_rule_pack(regra="scan", cliente="Padrão")
    skill = agent_loader.choose_skill("Analise este payload de firewall")
    contexts = agent_loader.build_prompt_context(user_input="payload suspeito", selected_skill=skill)

    check("migration_input_adapter_legacy_pointer", input_adapter.LEGACY_MODULE == "soc_copilot.modules.input_adapter")
    check("migration_input_adapter_adapt", adapted_fmt in {"text", "json", "csv", "fortigate"} and bool(adapted_raw))
    check("migration_parser_legacy_pointer", parser.LEGACY_MODULE == "soc_copilot.modules.parser_engine")
    check("migration_parser_parse", isinstance(parsed, dict) and "IOCs" in parsed)
    check("migration_engine_prepare_payload", isinstance(prepared.get("fields"), dict) and prepared.get("format") == adapted_fmt)
    check("migration_analysis_pack", hasattr(pack, "modelo_nome"))
    check("migration_chat_legacy_pointer", chat.LEGACY_MODULE == "soc_copilot.modules.chat_service")
    check("migration_storage_legacy_pointer", storage.LEGACY_MODULE == "soc_copilot.modules.persistence")
    check("migration_agent_loader_context", isinstance(contexts, dict) and "identity" in contexts)

    storage.ensure_chat_session("migration-session", cliente="Teste", titulo="Sessao de migracao")
    storage.save_chat_message("migration-session", "user", "Mensagem de teste", skill="triage")
    history = storage.list_chat_messages("migration-session", limit=5)
    sessions = storage.list_chat_sessions(limit=5)
    check("migration_storage_history", len(history) == 1 and history[0]["content"] == "Mensagem de teste")
    check("migration_storage_sessions", any(item.get("session_id") == "migration-session" for item in sessions))

    original_enrich = threat_intel.ti_adapter.enrich
    try:
        threat_intel.ti_adapter.enrich = lambda iocs: {"8.8.8.8": "stub-ok"}  # type: ignore[assignment]
        enriched = threat_intel.enrich_iocs({"ips": ["8.8.8.8"]})
        check("migration_ti_gateway", enriched.get("8.8.8.8") == "stub-ok")
    finally:
        threat_intel.ti_adapter.enrich = original_enrich  # type: ignore[assignment]
except Exception as exc:
    check("runtime_migration_map_flow", False, str(exc))
finally:
    legacy_persistence.DB_PATH = original_db_path
    tmpdir.cleanup()


print(f"\n{'='*60}")
print(f"SOCC Runtime — Migration Map  ({len(resultados)} checks)")
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
