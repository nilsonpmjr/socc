"""
Valida contrato interno do runtime e o comando inicial `socc chat`.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from socc.cli.main import main
from socc.cli import service_manager
from socc.core import CONTRACT_VERSION
from socc.core.engine import analyze_payload
from socc.core import engine as engine_module
from socc.core.tools import invoke_tool, list_tools
from socc.gateway import vantage_api as vantage_gateway

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


try:
    check("tool_registry_has_extract_iocs", "extract_iocs" in list_tools())
    tool_ok = invoke_tool("defang", {"text": "http://example.com"})
    tool_missing = invoke_tool("nao_existe", {})
    check("tool_contract_version", tool_ok.get("contract_version") == CONTRACT_VERSION)
    check("tool_invoke_success", tool_ok.get("ok") is True and "[.]" in str(tool_ok.get("output")))
    check("tool_invoke_missing", tool_missing.get("ok") is False and tool_missing.get("error") == "tool_not_found")

    payload = "srcip=10.0.0.5 dstip=8.8.8.8 action=blocked user=teste@example.com"
    analysis = analyze_payload(payload_text=payload, include_draft=False)
    check("analysis_contract_version", analysis.get("contract_version") == CONTRACT_VERSION)
    check("analysis_has_gateway_contract", isinstance(analysis.get("gateway"), dict))
    check("analysis_has_tool_results", isinstance(analysis.get("tool_results"), list))

    tmpdir = tempfile.TemporaryDirectory()
    runtime_home = Path(tmpdir.name) / ".socc-intel-cli"
    docs_dir = Path(tmpdir.name) / "intel-docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "kb.md").write_text("# KB\n\nDocumento de teste para ingestão local.\n", encoding="utf-8")

    intel_add_stdout = io.StringIO()
    with redirect_stdout(intel_add_stdout):
        exit_code = main(
            [
                "intel",
                "--home",
                str(runtime_home),
                "add-source",
                "--id",
                "kb-test",
                "--name",
                "KB Test",
                "--path",
                str(docs_dir),
                "--json",
            ]
        )
    intel_add_payload = json.loads(intel_add_stdout.getvalue())
    check("cli_intel_add_exit_code", exit_code == 0)
    check("cli_intel_add_payload", (intel_add_payload.get("source") or {}).get("id") == "kb-test")

    intel_ingest_stdout = io.StringIO()
    with redirect_stdout(intel_ingest_stdout):
        exit_code = main(["intel", "--home", str(runtime_home), "ingest", "--source-id", "kb-test", "--json"])
    intel_ingest_payload = json.loads(intel_ingest_stdout.getvalue())
    check("cli_intel_ingest_exit_code", exit_code == 0)
    check("cli_intel_ingest_chunks", int(intel_ingest_payload.get("chunks_indexed") or 0) >= 1)

    intel_list_stdout = io.StringIO()
    with redirect_stdout(intel_list_stdout):
        exit_code = main(["intel", "--home", str(runtime_home), "list", "--json"])
    intel_list_payload = json.loads(intel_list_stdout.getvalue())
    check("cli_intel_list_exit_code", exit_code == 0)
    check("cli_intel_list_source", any(item.get("id") == "kb-test" for item in intel_list_payload.get("sources", [])))

    onboard_stdout = io.StringIO()
    with redirect_stdout(onboard_stdout):
        exit_code = main(["onboard", "--home", str(runtime_home), "--json"])
    onboard_payload = json.loads(onboard_stdout.getvalue())
    check("cli_onboard_exit_code", exit_code == 0)
    check("cli_onboard_has_bootstrap", isinstance(onboard_payload.get("bootstrap"), dict))
    check("cli_onboard_has_doctor", isinstance(onboard_payload.get("doctor"), dict))

    doctor_stdout = io.StringIO()
    with redirect_stdout(doctor_stdout):
        exit_code = main(["doctor", "--home", str(runtime_home), "--json"])
    doctor_payload = json.loads(doctor_stdout.getvalue())
    check("cli_doctor_exit_code", exit_code == 0)
    check("cli_doctor_checks", isinstance(doctor_payload.get("checks"), dict))
    check("cli_doctor_intel", isinstance(doctor_payload.get("intel"), dict))

    original_start_service = service_manager.start_service
    original_stop_service = service_manager.stop_service
    original_restart_service = service_manager.restart_service
    original_service_status = service_manager.service_status
    original_dashboard_url = service_manager.dashboard_url
    original_open_dashboard = service_manager.open_dashboard
    try:
        service_manager.start_service = lambda **kwargs: {
            "started": True,
            "running": True,
            "pid": 4242,
            "url": "http://127.0.0.1:8080",
            "pid_file": "/tmp/socc-serve.pid",
            "stdout_log": "/tmp/socc-serve.out.log",
            "stderr_log": "/tmp/socc-serve.err.log",
        }
        service_manager.stop_service = lambda home=None: {
            "stopped": True,
            "was_running": True,
            "pid": 4242,
        }
        service_manager.restart_service = lambda **kwargs: {
            "restarted": True,
            "running": True,
            "pid": 4343,
            "url": "http://127.0.0.1:8080",
        }
        service_manager.service_status = lambda home=None: {
            "running": True,
            "pid": 4242,
            "pid_file": "/tmp/socc-serve.pid",
        }
        service_manager.dashboard_url = lambda home=None, host="127.0.0.1", port=8080: {
            "url": "http://127.0.0.1:8080",
            "running": True,
            "pid": 4242,
        }
        service_manager.open_dashboard = lambda home=None, host="127.0.0.1", port=8080: {
            "url": "http://127.0.0.1:8080",
            "running": True,
            "pid": 4242,
            "opened": True,
            "error": "",
        }

        service_start_stdout = io.StringIO()
        with redirect_stdout(service_start_stdout):
            exit_code = main(["service", "--home", str(runtime_home), "start", "--json"])
        service_start_payload = json.loads(service_start_stdout.getvalue())
        check("cli_service_start_exit_code", exit_code == 0)
        check("cli_service_start_running", service_start_payload.get("running") is True)

        gateway_start_stdout = io.StringIO()
        with redirect_stdout(gateway_start_stdout):
            exit_code = main(["gateway", "--home", str(runtime_home), "start", "--json"])
        gateway_start_payload = json.loads(gateway_start_stdout.getvalue())
        check("cli_gateway_start_exit_code", exit_code == 0)
        check("cli_gateway_start_running", gateway_start_payload.get("running") is True)

        service_restart_stdout = io.StringIO()
        with redirect_stdout(service_restart_stdout):
            exit_code = main(["service", "--home", str(runtime_home), "restart", "--json"])
        service_restart_payload = json.loads(service_restart_stdout.getvalue())
        check("cli_service_restart_exit_code", exit_code == 0)
        check("cli_service_restart_flag", service_restart_payload.get("restarted") is True)
        check("cli_service_restart_pid", service_restart_payload.get("pid") == 4343)

        service_status_stdout = io.StringIO()
        with redirect_stdout(service_status_stdout):
            exit_code = main(["service", "--home", str(runtime_home), "status", "--json"])
        service_status_payload = json.loads(service_status_stdout.getvalue())
        check("cli_service_status_exit_code", exit_code == 0)
        check("cli_service_status_pid", service_status_payload.get("pid") == 4242)

        service_stop_stdout = io.StringIO()
        with redirect_stdout(service_stop_stdout):
            exit_code = main(["service", "--home", str(runtime_home), "stop", "--json"])
        service_stop_payload = json.loads(service_stop_stdout.getvalue())
        check("cli_service_stop_exit_code", exit_code == 0)
        check("cli_service_stop_flag", service_stop_payload.get("stopped") is True)

        gateway_stop_stdout = io.StringIO()
        with redirect_stdout(gateway_stop_stdout):
            exit_code = main(["gateway", "--home", str(runtime_home), "stop", "--json"])
        gateway_stop_payload = json.loads(gateway_stop_stdout.getvalue())
        check("cli_gateway_stop_exit_code", exit_code == 0)
        check("cli_gateway_stop_flag", gateway_stop_payload.get("stopped") is True)

        dashboard_stdout = io.StringIO()
        with redirect_stdout(dashboard_stdout):
            exit_code = main(["dashboard", "--home", str(runtime_home), "--json"])
        dashboard_payload = json.loads(dashboard_stdout.getvalue())
        check("cli_dashboard_exit_code", exit_code == 0)
        check("cli_dashboard_url", dashboard_payload.get("url") == "http://127.0.0.1:8080")

        dashboard_open_stdout = io.StringIO()
        with redirect_stdout(dashboard_open_stdout):
            exit_code = main(["dashboard", "--home", str(runtime_home), "--open", "--json"])
        dashboard_open_payload = json.loads(dashboard_open_stdout.getvalue())
        check("cli_dashboard_open_exit_code", exit_code == 0)
        check("cli_dashboard_open_flag", dashboard_open_payload.get("opened") is True)
    finally:
        service_manager.start_service = original_start_service
        service_manager.stop_service = original_stop_service
        service_manager.restart_service = original_restart_service
        service_manager.service_status = original_service_status
        service_manager.dashboard_url = original_dashboard_url
        service_manager.open_dashboard = original_open_dashboard

    original_chat_reply = engine_module.chat_reply
    original_stream_chat_events = engine_module.stream_chat_events
    original_vantage_status = vantage_gateway.status_payload
    original_vantage_probe = vantage_gateway.probe_module
    try:
        engine_module.chat_reply = lambda message, session_id="", cliente="", response_mode="balanced": {
            "contract_version": CONTRACT_VERSION,
            "type": "message",
            "session_id": session_id or "sessao-cli",
            "skill": "triage",
            "content": f"eco: {message}",
            "metadata": {"response_mode": response_mode},
            "runtime": {"provider": "stub"},
            "gateway": {"provider": "stub", "contract_version": CONTRACT_VERSION},
        }
        engine_module.stream_chat_events = lambda message, session_id="", cliente="", response_mode="balanced": iter(
            [
                {"event": "meta", "session_id": session_id or "sessao-stream", "skill": "triage"},
                {"event": "delta", "delta": "eco"},
                {"event": "delta", "delta": ": "},
                {"event": "delta", "delta": message},
                {
                    "event": "final",
                    "data": {
                        "contract_version": CONTRACT_VERSION,
                        "type": "message",
                        "session_id": session_id or "sessao-stream",
                        "skill": "triage",
                        "content": f"eco: {message}",
                        "metadata": {"response_mode": response_mode},
                        "runtime": {"provider": "stub"},
                        "gateway": {"provider": "stub", "contract_version": CONTRACT_VERSION},
                    },
                },
            ]
        )

        json_stdout = io.StringIO()
        with redirect_stdout(json_stdout):
            exit_code = main(["chat", "--message", "olá runtime", "--response-mode", "fast", "--json"])
        json_payload = json.loads(json_stdout.getvalue())
        check("cli_chat_json_exit_code", exit_code == 0)
        check("cli_chat_json_payload", json_payload.get("content") == "eco: olá runtime")
        check("cli_chat_json_response_mode", (json_payload.get("metadata") or {}).get("response_mode") == "fast")

        stream_stdout = io.StringIO()
        with redirect_stdout(stream_stdout):
            exit_code = main(["chat", "--message", "olá runtime", "--stream"])
        check("cli_chat_stream_exit_code", exit_code == 0)
        check("cli_chat_stream_output", "eco: olá runtime" in stream_stdout.getvalue())

        vantage_gateway.status_payload = lambda: {
            "enabled": True,
            "configured": True,
            "base_url": "https://vantage.local",
            "auth_mode": "bearer",
            "timeout_seconds": 12,
            "verify_tls": True,
            "catalog_size": 2,
            "selected_modules": ["feed", "hunting"],
            "modules": [
                {"id": "feed", "path": "/api/feed", "selected": True},
                {"id": "hunting", "path": "/api/hunting", "selected": True},
            ],
            "future_rss_via_api": True,
        }
        vantage_gateway.probe_module = lambda module_id: {
            "ok": module_id == "feed",
            "module": module_id,
            "status_code": 200 if module_id == "feed" else None,
            "error": "" if module_id == "feed" else "not found",
        }

        vantage_status_stdout = io.StringIO()
        with redirect_stdout(vantage_status_stdout):
            exit_code = main(["vantage", "status", "--json"])
        vantage_status_payload = json.loads(vantage_status_stdout.getvalue())
        check("cli_vantage_status_exit_code", exit_code == 0)
        check("cli_vantage_status_enabled", vantage_status_payload.get("enabled") is True)

        vantage_modules_stdout = io.StringIO()
        with redirect_stdout(vantage_modules_stdout):
            exit_code = main(["vantage", "modules", "--json"])
        vantage_modules_payload = json.loads(vantage_modules_stdout.getvalue())
        check("cli_vantage_modules_exit_code", exit_code == 0)
        check(
            "cli_vantage_modules_feed",
            any(item.get("id") == "feed" for item in vantage_modules_payload.get("modules", [])),
        )

        vantage_probe_stdout = io.StringIO()
        with redirect_stdout(vantage_probe_stdout):
            exit_code = main(["vantage", "probe", "--module", "feed", "--json"])
        vantage_probe_payload = json.loads(vantage_probe_stdout.getvalue())
        check("cli_vantage_probe_exit_code", exit_code == 0)
        check("cli_vantage_probe_ok", vantage_probe_payload.get("ok") is True)
    finally:
        engine_module.chat_reply = original_chat_reply
        engine_module.stream_chat_events = original_stream_chat_events
        vantage_gateway.status_payload = original_vantage_status
        vantage_gateway.probe_module = original_vantage_probe
        try:
            tmpdir.cleanup()
        except Exception:
            pass
except Exception as exc:
    check("contracts_cli_flow", False, str(exc))


print(f"\n{'='*60}")
print(f"SOCC Runtime — Contracts + CLI  ({len(resultados)} checks)")
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
