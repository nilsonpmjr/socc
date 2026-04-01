from __future__ import annotations

import argparse
import json
import os
import sys
from time import time
from pathlib import Path

from socc.cli.installer import bootstrap_runtime


def _read_text_input(
    args: argparse.Namespace,
    *,
    text_attr: str,
    file_attr: str,
    empty_message: str,
) -> str:
    text_value = getattr(args, text_attr, "")
    if text_value:
        return text_value
    file_value = getattr(args, file_attr, "")
    if file_value:
        return Path(file_value).read_text(encoding="utf-8", errors="replace")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit(empty_message)


def _read_payload(args: argparse.Namespace) -> str:
    return _read_text_input(
        args,
        text_attr="text",
        file_attr="file",
        empty_message="Provide --file, --text, or pipe a payload to stdin.",
    )


def _read_chat_message(args: argparse.Namespace) -> str:
    return _read_text_input(
        args,
        text_attr="message",
        file_attr="file",
        empty_message="Provide --message, --file, use --interactive, or pipe text to stdin.",
    )


def _runtime_home_arg(value: str | None) -> Path | None:
    return Path(value).expanduser() if value else None


def _doctor_payload(home: Path | None = None, *, include_probe: bool = False) -> dict[str, object]:
    from socc.cli.installer import package_root, runtime_agent_home, runtime_home
    from socc.core.knowledge_base import inspect_index
    from socc.gateway import vantage_api

    runtime_dir = runtime_home(home)
    manifest_file = runtime_dir / "socc.json"
    manifest_payload: dict[str, object] = {}
    if manifest_file.exists():
        try:
            manifest_payload = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception:
            manifest_payload = {}
    installation_layout = str((((manifest_payload.get("meta") or {}) if isinstance(manifest_payload, dict) else {}).get("installation_layout") or "checkout"))
    intel = inspect_index(home)
    env_error = ""
    runtime_error = ""
    features_error = ""
    env_paths = {"runtime_env": str(runtime_dir / ".env"), "repo_env": ""}
    runtime_payload: dict[str, object] = {
        "runtime": {
            "enabled": False,
            "provider": "unavailable",
            "model": "",
            "device": "unknown",
        }
    }
    feature_payload: dict[str, object] = {}

    try:
        from socc.utils.config_loader import load_environment

        env_paths = load_environment()
    except Exception as exc:  # pragma: no cover - degradacao de install minimo
        env_error = f"{type(exc).__name__}: {exc}"

    try:
        from socc.gateway.llm_gateway import probe_inference_backend, runtime_status

        runtime_payload = runtime_status()
    except Exception as exc:  # pragma: no cover - degradacao de install minimo
        runtime_error = f"{type(exc).__name__}: {exc}"

        def probe_inference_backend() -> dict[str, object]:
            return {
                "reachable": False,
                "latency_ms": None,
                "error": runtime_error,
            }

    try:
        from socc.utils.feature_flags import feature_flags_payload

        feature_payload = feature_flags_payload()
    except Exception as exc:  # pragma: no cover - degradacao de install minimo
        features_error = f"{type(exc).__name__}: {exc}"

    payload: dict[str, object] = {
        "paths": {
            "runtime_home": str(runtime_dir),
            "agent_home": str(runtime_agent_home(home)),
            "package_root": str(package_root()),
            "installation_layout": installation_layout,
            "env_file": str(runtime_dir / ".env"),
            "manifest_file": str(runtime_dir / "socc.json"),
            "intel_registry": ((intel.get("paths") or {}).get("registry") or ""),
            "intel_index": ((intel.get("paths") or {}).get("index") or ""),
            "runtime_env_loaded_from": env_paths.get("runtime_env"),
            "repo_env_loaded_from": env_paths.get("repo_env"),
        },
        "checks": {
            "runtime_home_exists": runtime_dir.exists(),
            "env_file_exists": (runtime_dir / ".env").exists(),
            "manifest_exists": (runtime_dir / "socc.json").exists(),
            "agent_home_exists": runtime_agent_home(home).exists(),
            "intel_registry_exists": Path(str((intel.get("paths") or {}).get("registry") or "")).exists(),
            "intel_index_exists": Path(str((intel.get("paths") or {}).get("index") or "")).exists(),
        },
        "runtime": runtime_payload,
        "features": feature_payload,
        "intel": intel.get("manifest", {}),
        "vantage": vantage_api.status_payload(),
    }
    dependency_notes = {
        "env_loader_error": env_error,
        "runtime_error": runtime_error,
        "feature_flags_error": features_error,
    }
    dependency_notes = {key: value for key, value in dependency_notes.items() if value}
    if dependency_notes:
        payload["dependency_warnings"] = dependency_notes
    if include_probe:
        payload["probe"] = probe_inference_backend()
    return payload


def _print_doctor(payload: dict[str, object]) -> None:
    paths = payload.get("paths", {}) if isinstance(payload, dict) else {}
    checks = payload.get("checks", {}) if isinstance(payload, dict) else {}
    runtime = ((payload.get("runtime", {}) or {}).get("runtime", {}) or {}) if isinstance(payload, dict) else {}
    intel = payload.get("intel", {}) if isinstance(payload, dict) else {}
    vantage = payload.get("vantage", {}) if isinstance(payload, dict) else {}
    print("SOCC Doctor:")
    for key in ("runtime_home", "agent_home", "env_file", "manifest_file", "intel_registry", "intel_index"):
        print(f"- {key}: {paths.get(key) or '-'}")
    print(f"- package_root: {paths.get('package_root') or '-'}")
    print(f"- installation_layout: {paths.get('installation_layout') or '-'}")
    print("\nChecks:")
    for key in sorted(checks):
        print(f"- {key}: {checks.get(key)}")
    print("\nRuntime:")
    print(f"- backend: {runtime.get('backend')}")
    print(f"- backend_label: {runtime.get('backend_label')}")
    print(f"- enabled: {runtime.get('enabled')}")
    print(f"- provider: {runtime.get('provider')}")
    print(f"- model: {runtime.get('model')}")
    print(f"- device: {runtime.get('device')}")
    print("\nKnowledge Base:")
    print(f"- index_version: {intel.get('version')}")
    print(f"- indexed_documents: {intel.get('indexed_documents', 0)}")
    print(f"- indexed_chunks: {intel.get('indexed_chunks', 0)}")
    print("\nVantage:")
    print(f"- enabled: {vantage.get('enabled')}")
    print(f"- configured: {vantage.get('configured')}")
    print(f"- base_url: {vantage.get('base_url') or '-'}")
    print(f"- auth_mode: {vantage.get('auth_mode')}")
    print(f"- selected_modules: {', '.join(vantage.get('selected_modules', [])) or '-'}")
    probe = payload.get("probe")
    if isinstance(probe, dict):
        print("\nProbe:")
        print(f"- reachable: {probe.get('reachable')}")
        print(f"- latency_ms: {probe.get('latency_ms')}")
        print(f"- error: {probe.get('error') or '-'}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="socc", description="SOCC local runtime CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create ~/.socc and seed local runtime files")
    init_parser.add_argument("--home", help="Alternative runtime home directory")
    init_parser.add_argument("--force", action="store_true", help="Overwrite generated runtime files")

    onboard_parser = subparsers.add_parser("onboard", help="Bootstrap and validate the local runtime, inspired by OpenClaw onboarding")
    onboard_parser.add_argument("--home", help="Alternative runtime home directory")
    onboard_parser.add_argument("--force", action="store_true", help="Overwrite generated runtime files")
    onboard_parser.add_argument("--probe", action="store_true", help="Probe the configured inference backend after bootstrap")
    onboard_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    onboard_parser.add_argument("--no-interactive", action="store_true", help="Skip interactive wizard (flag-only mode)")

    doctor_parser = subparsers.add_parser("doctor", help="Run local runtime diagnostics")
    doctor_parser.add_argument("--home", help="Alternative runtime home directory")
    doctor_parser.add_argument("--probe", action="store_true", help="Probe the configured inference backend")
    doctor_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    service_parser = subparsers.add_parser(
        "service",
        aliases=["gateway"],
        help="Manage the local SOCC web service",
    )
    service_parser.add_argument("--home", help="Alternative runtime home directory")
    service_subparsers = service_parser.add_subparsers(dest="service_command", required=True)

    service_start = service_subparsers.add_parser("start", help="Start the local web service in background")
    service_start.add_argument("--host", default="127.0.0.1", help="Bind host")
    service_start.add_argument("--port", type=int, default=8080, help="Bind port")
    service_start.add_argument("--log-level", default="info", help="Uvicorn log level")
    service_start.add_argument("--json", action="store_true", help="Emit JSON output")

    service_stop = service_subparsers.add_parser("stop", help="Stop the background local web service")
    service_stop.add_argument("--json", action="store_true", help="Emit JSON output")

    service_restart = service_subparsers.add_parser("restart", help="Restart the background local web service")
    service_restart.add_argument("--host", default="127.0.0.1", help="Bind host")
    service_restart.add_argument("--port", type=int, default=8080, help="Bind port")
    service_restart.add_argument("--log-level", default="info", help="Uvicorn log level")
    service_restart.add_argument("--json", action="store_true", help="Emit JSON output")

    service_status = service_subparsers.add_parser("status", help="Inspect background local web service status")
    service_status.add_argument("--json", action="store_true", help="Emit JSON output")

    dashboard_parser = subparsers.add_parser("dashboard", help="Show the local dashboard URL")
    dashboard_parser.add_argument("--home", help="Alternative runtime home directory")
    dashboard_parser.add_argument("--host", default="127.0.0.1", help="Fallback host when service metadata is absent")
    dashboard_parser.add_argument("--port", type=int, default=8080, help="Fallback port when service metadata is absent")
    dashboard_parser.add_argument("--open", action="store_true", help="Try to open the dashboard in the default browser")
    dashboard_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    serve_parser = subparsers.add_parser("serve", help="Start the current SOCC web application")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    serve_parser.add_argument("--port", type=int, help="Bind port override")
    serve_parser.add_argument("--reload", action="store_true", help="Enable autoreload")
    serve_parser.add_argument("--log-level", default="info", help="Uvicorn log level")

    runtime_parser = subparsers.add_parser("runtime", help="Show runtime provider, device, and observability status")
    runtime_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    runtime_parser.add_argument("--benchmark", action="store_true", help="Run a lightweight concurrency/runtime benchmark")
    runtime_parser.add_argument("--probe", action="store_true", help="Probe the configured inference backend")
    runtime_parser.add_argument("--concurrency", type=int, default=4, help="Worker count for runtime benchmark")
    runtime_parser.add_argument("--hold-ms", type=int, default=150, help="How long each synthetic worker holds the runtime guard")

    analyze_parser = subparsers.add_parser("analyze", help="Parse a payload and optionally draft an output")
    analyze_parser.add_argument("--file", help="Payload file to analyze")
    analyze_parser.add_argument("--text", help="Inline payload text")
    analyze_parser.add_argument("--cliente", default="", help="Client name for model selection")
    analyze_parser.add_argument("--regra", default="", help="Rule context for model selection")
    analyze_parser.add_argument("--classificacao", default="TP", help="Draft classification")
    analyze_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    analyze_parser.add_argument("--no-draft", action="store_true", help="Skip draft generation")

    chat_parser = subparsers.add_parser("chat", help="Send a message to the SOCC runtime chat")

    tui_parser = subparsers.add_parser("tui", help="Start full-screen TUI chat")
    tui_parser.add_argument("--session-id", default="", help="Reuse an existing session id")
    tui_parser.add_argument("--cliente", default="", help="Client context")
    tui_parser.add_argument("--backend", default="", help="Backend LLM: anthropic | ollama | openai")
    tui_parser.add_argument("--model", default="", help="Model override")
    tui_parser.add_argument(
        "--mode", dest="response_mode", default="balanced",
        choices=["fast", "balanced", "deep"],
        help="Response mode (default: balanced)",
    )
    chat_parser.add_argument("--message", help="Inline chat message")
    chat_parser.add_argument("--file", help="Read the chat message from a file")
    chat_parser.add_argument("--session-id", default="", help="Reuse an existing session id")
    chat_parser.add_argument("--cliente", default="", help="Client context passed to the chat runtime")
    chat_parser.add_argument(
        "--response-mode",
        default="balanced",
        choices=["fast", "balanced", "deep"],
        help="Response profile tuned for speed vs depth",
    )
    chat_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    chat_parser.add_argument("--stream", action="store_true", default=True, help="Stream reply chunks to stdout")
    chat_parser.add_argument("--interactive", action="store_true", help="Start full-screen TUI chat")
    chat_parser.add_argument("--backend", default="", help="Backend LLM: anthropic | ollama | openai")
    chat_parser.add_argument("--model", default="", help="Model override (e.g. claude-haiku-4-5-20251001)")

    intel_parser = subparsers.add_parser("intel", help="Manage local intelligence sources and RAG ingestion")
    intel_parser.add_argument("--home", help="Alternative runtime home directory")
    intel_subparsers = intel_parser.add_subparsers(dest="intel_command", required=True)

    intel_list = intel_subparsers.add_parser("list", help="List registered sources and index stats")
    intel_list.add_argument("--json", action="store_true", help="Emit JSON output")

    intel_add = intel_subparsers.add_parser("add-source", help="Register a local source for future ingestion")
    intel_add.add_argument("--id", required=True, help="Stable source identifier")
    intel_add.add_argument("--name", required=True, help="Display name")
    intel_add.add_argument("--kind", default="document_set", help="Source kind, e.g. document_set or case_notes")
    intel_add.add_argument("--trust", default="internal", help="Trust level, e.g. internal or curated_external")
    intel_add.add_argument("--path", default="", help="File or directory to ingest from")
    intel_add.add_argument("--tags", default="", help="Comma-separated tags")
    intel_add.add_argument("--description", default="", help="Short source description")
    intel_add.add_argument("--json", action="store_true", help="Emit JSON output")

    intel_ingest = intel_subparsers.add_parser("ingest", help="Normalize and index a registered source")
    intel_ingest.add_argument("--source-id", required=True, help="Registered source id")
    intel_ingest.add_argument("--path", default="", help="Optional file or directory override")
    intel_ingest.add_argument("--json", action="store_true", help="Emit JSON output")

    # ---- configure ----
    configure_parser = subparsers.add_parser("configure", help="Manage runtime configuration")
    configure_parser.add_argument("--home", help="Alternative runtime home directory")
    configure_subparsers = configure_parser.add_subparsers(dest="configure_command", required=True)

    configure_show = configure_subparsers.add_parser("show", help="Show active configuration (secrets redacted)")
    configure_show.add_argument("--json", action="store_true", help="Emit JSON output")

    configure_set = configure_subparsers.add_parser("set", help="Set a configuration key")
    configure_set.add_argument("key", help="Environment variable name")
    configure_set.add_argument("value", help="Value to set")
    configure_set.add_argument("--json", action="store_true", help="Emit JSON output")

    configure_unset = configure_subparsers.add_parser("unset", help="Comment out a configuration key")
    configure_unset.add_argument("key", help="Environment variable name")
    configure_unset.add_argument("--json", action="store_true", help="Emit JSON output")

    configure_validate = configure_subparsers.add_parser("validate", help="Validate current configuration")
    configure_validate.add_argument("--json", action="store_true", help="Emit JSON output")

    # ---- models ----
    models_parser = subparsers.add_parser("models", help="Manage LLM models")
    models_subparsers = models_parser.add_subparsers(dest="models_command", required=True)

    models_list = models_subparsers.add_parser("list", help="List available models from active backends")
    models_list.add_argument("--json", action="store_true", help="Emit JSON output")

    models_set = models_subparsers.add_parser("set", help="Set a model profile")
    models_set.add_argument("model", help="Model name")
    models_set_group = models_set.add_mutually_exclusive_group(required=True)
    models_set_group.add_argument("--fast", action="store_true", help="Set as Fast profile")
    models_set_group.add_argument("--balanced", action="store_true", help="Set as Balanced profile")
    models_set_group.add_argument("--deep", action="store_true", help="Set as Deep profile")
    models_set.add_argument("--json", action="store_true", help="Emit JSON output")

    models_fallback = models_subparsers.add_parser("fallback", help="Manage fallback provider chain")
    models_fallback_sub = models_fallback.add_subparsers(dest="fallback_command", required=True)

    fb_list = models_fallback_sub.add_parser("list", help="Show current fallback configuration")
    fb_list.add_argument("--json", action="store_true", help="Emit JSON output")

    fb_add = models_fallback_sub.add_parser("add", help="Set fallback provider")
    fb_add.add_argument("provider", help="Provider name (anthropic, ollama, cpu, deterministic, etc.)")
    fb_add.add_argument("--json", action="store_true", help="Emit JSON output")

    fb_remove = models_fallback_sub.add_parser("remove", help="Disable fallback provider")
    fb_remove.add_argument("--json", action="store_true", help="Emit JSON output")

    models_test = models_subparsers.add_parser("test", help="Smoke test inference with a model")
    models_test.add_argument("--model", default="", help="Model to test (default: current balanced)")
    models_test.add_argument("--json", action="store_true", help="Emit JSON output")

    # ---- train ----
    train_parser = subparsers.add_parser(
        "train",
        help="Treinar o modelo ML com os arquivos Pensamento_Ofensa_*.md do diretório Training",
    )
    train_parser.add_argument("--home", help="Diretório home alternativo do runtime")
    train_parser.add_argument(
        "--force",
        action="store_true",
        help="Forçar retreinamento mesmo que o modelo esteja atualizado",
    )
    train_parser.add_argument(
        "--dir",
        dest="training_dir",
        default="",
        help="Caminho alternativo para o diretório Training (padrão: .agents/Training)",
    )
    train_parser.add_argument("--json", action="store_true", help="Emitir saída em JSON")
    train_parser.add_argument(
        "--status",
        action="store_true",
        help="Exibir status do modelo sem treinar",
    )
    train_parser.add_argument(
        "--list",
        action="store_true",
        help="Listar casos de treinamento disponíveis",
    )
    train_parser.add_argument(
        "--predict",
        default="",
        metavar="TEXTO",
        help="Inferir classificação para um texto ou caminho de arquivo",
    )
    train_parser.add_argument(
        "--predict-file",
        default="",
        metavar="ARQUIVO",
        help="Inferir classificação a partir de um arquivo de payload",
    )

    # ---- vantage ----
    vantage_parser = subparsers.add_parser("vantage", help="Inspect Vantage API integration status and module catalog")
    vantage_subparsers = vantage_parser.add_subparsers(dest="vantage_command", required=True)

    vantage_status = vantage_subparsers.add_parser("status", help="Show Vantage API integration status")
    vantage_status.add_argument("--json", action="store_true", help="Emit JSON output")

    vantage_modules = vantage_subparsers.add_parser("modules", help="List mapped Vantage modules for SOCC")
    vantage_modules.add_argument("--json", action="store_true", help="Emit JSON output")

    vantage_probe = vantage_subparsers.add_parser("probe", help="Probe a mapped Vantage module")
    vantage_probe.add_argument("--module", required=True, help="Mapped module id, e.g. feed or hunting")
    vantage_probe.add_argument("--json", action="store_true", help="Emit JSON output")

    return parser


def _run_interactive_chat(args: argparse.Namespace) -> int:
    # Bootstrap runtime (non-blocking daemon thread)
    from socc.cli.startup import startup
    startup(verbose=getattr(args, "verbose", False))

    try:
        from socc.cli.chat_interactive import run_chat_tui
        return run_chat_tui(
            session_id=args.session_id or "",
            cliente=args.cliente or "",
            response_mode=getattr(args, "response_mode", "balanced"),
            selected_backend=getattr(args, "backend", "") or "",
            selected_model=getattr(args, "model", "") or "",
            stream=getattr(args, "stream", True),
        )
    except ImportError:
        pass

    # fallback plain REPL
    from socc.core.engine import chat_reply, stream_chat_events
    session_id = args.session_id or str(int(time() * 1000))
    print("SOCC chat interativo. Digite /exit para sair.")
    print(f"Sessao: {session_id}")
    while True:
        try:
            message = input("voce> ").strip()
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            return 0
        if not message:
            continue
        if message.lower() in {"/exit", "exit", "quit", "/quit"}:
            return 0
        if args.stream and not args.json:
            print("socc> ", end="", flush=True)
            final_payload: dict[str, object] | None = None
            for event in stream_chat_events(
                message,
                session_id=session_id,
                cliente=args.cliente,
                response_mode=args.response_mode,
            ):
                if event.get("event") == "delta":
                    print(str(event.get("delta") or ""), end="", flush=True)
                elif event.get("event") == "final":
                    data = event.get("data")
                    if isinstance(data, dict):
                        final_payload = data
            print()
            if isinstance(final_payload, dict):
                session_id = str(final_payload.get("session_id") or session_id)
        else:
            response = chat_reply(
                message,
                session_id=session_id,
                cliente=args.cliente,
                response_mode=args.response_mode,
            )
            session_id = str(response.get("session_id") or session_id)
            print(f"socc> {response.get('content') or response.get('message') or ''}")


def _chat_requires_interactive(args: argparse.Namespace) -> bool:
    return bool(
        args.interactive
        or (
            not args.message
            and not args.file
            and sys.stdin.isatty()
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        result = bootstrap_runtime(Path(args.home).expanduser() if args.home else None, force=args.force)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "onboard":
        home = _runtime_home_arg(args.home)
        bootstrap = bootstrap_runtime(home, force=args.force)

        # Interactive wizard when TTY is available and not suppressed
        use_wizard = (
            sys.stdin.isatty()
            and not getattr(args, "json", False)
            and not getattr(args, "no_interactive", False)
        )
        if use_wizard:
            from socc.cli.onboard_wizard import run_onboard_wizard

            wizard_result = run_onboard_wizard(home)
            doctor = _doctor_payload(home, include_probe=args.probe)
            payload = {"bootstrap": bootstrap, "wizard": wizard_result, "doctor": doctor}
            return 0

        # Non-interactive fallback (original behavior)
        doctor = _doctor_payload(home, include_probe=args.probe)
        payload = {
            "bootstrap": bootstrap,
            "doctor": doctor,
            "next_steps": [
                "Revise ~/.socc/.env e ajuste provider/modelo conforme o ambiente.",
                "Use `socc doctor --probe` para validar o backend de inferência.",
                "Use `socc intel add-source` e `socc intel ingest` para preparar a base local de conhecimento.",
                "Suba a interface com `socc serve`.",
            ],
        }
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("SOCC Onboard:")
            print(f"- runtime_home: {bootstrap.get('runtime_home')}")
            print(f"- agent_home: {bootstrap.get('agent_home')}")
            print(f"- env_file: {bootstrap.get('env_file')}")
            print()
            _print_doctor(doctor)
            print("\nNext Steps:")
            for item in payload["next_steps"]:
                print(f"- {item}")
        return 0

    if args.command == "doctor":
        doctor = _doctor_payload(_runtime_home_arg(args.home), include_probe=args.probe)
        if args.json:
            print(json.dumps(doctor, indent=2, ensure_ascii=False))
        elif sys.stdin.isatty():
            from socc.cli.doctor_interactive import run_interactive_doctor
            run_interactive_doctor(doctor)
        else:
            _print_doctor(doctor)
        return 0

    if args.command in {"service", "gateway"}:
        from socc.cli.service_manager import (
            restart_service,
            service_status as service_status_payload,
            start_service,
            stop_service,
        )

        home = _runtime_home_arg(args.home)
        if args.service_command == "start":
            payload = start_service(
                host=args.host,
                port=args.port,
                log_level=args.log_level,
                home=home,
            )
        elif args.service_command == "restart":
            payload = restart_service(
                host=args.host,
                port=args.port,
                log_level=args.log_level,
                home=home,
            )
        elif args.service_command == "stop":
            payload = stop_service(home)
        else:
            payload = service_status_payload(home)

        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("SOCC Service:")
            for key in ("running", "started", "stopped", "already_running", "pid", "url", "pid_file", "stdout_log", "stderr_log"):
                if key in payload:
                    print(f"- {key}: {payload.get(key)}")
        return 0

    if args.command == "dashboard":
        from socc.cli.service_manager import dashboard_url, open_dashboard

        home = _runtime_home_arg(args.home)
        if args.open:
            payload = open_dashboard(
                home,
                host=args.host,
                port=args.port,
            )
        else:
            payload = dashboard_url(
                home,
                host=args.host,
                port=args.port,
            )
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(payload.get("url") or "")
        return 0

    if args.command == "serve":
        from socc.core.engine import serve

        serve(host=args.host, port=args.port, reload=args.reload, log_level=args.log_level)
        return 0

    if args.command == "runtime":
        from socc.gateway.llm_gateway import benchmark_runtime, probe_inference_backend, runtime_status
        from socc.utils.feature_flags import feature_flags_payload

        if args.benchmark:
            status = benchmark_runtime(
                concurrency=args.concurrency,
                hold_ms=args.hold_ms,
                include_probe=args.probe,
            )
        elif args.probe:
            status = {
                "status": runtime_status(),
                "probe": probe_inference_backend(),
            }
        else:
            status = runtime_status()
        status["features"] = feature_flags_payload()
        if args.json:
            print(json.dumps(status, indent=2, ensure_ascii=False))
        else:
            base = status.get("status", status)
            runtime = base.get("runtime", {})
            backends = base.get("backends", {})
            metrics = base.get("metrics", {})
            analysis_metrics = metrics.get("analysis_pipeline", {})
            gpu = ((base.get("resources", {}) or {}).get("gpu", {}) or {})
            features = status.get("features", {})
            safety = base.get("safety", {})
            print("Runtime:")
            print(f"- backend: {runtime.get('backend')}")
            print(f"- backend_label: {runtime.get('backend_label')}")
            print(f"- backend_source: {runtime.get('backend_source')}")
            print(f"- enabled: {runtime.get('enabled')}")
            print(f"- provider: {runtime.get('provider')}")
            print(f"- model: {runtime.get('model')}")
            print(f"- device: {runtime.get('device')}")
            print(f"- fallback_provider: {runtime.get('fallback_provider')}")
            print(f"- gpu_available: {runtime.get('gpu_available')}")
            print(f"- backend_gpu_supported: {runtime.get('backend_gpu_supported')}")
            print(f"- backend_streaming_supported: {runtime.get('backend_streaming_supported')}")
            print(f"- max_concurrency: {runtime.get('max_concurrency')}")
            supported = backends.get("supported", []) if isinstance(backends, dict) else []
            if supported:
                selected_line = ", ".join(
                    item.get("key", "")
                    for item in supported
                    if isinstance(item, dict) and item.get("selected")
                )
                print(f"- supported_backends: {len(supported)}")
                print(f"- selected_backend_from_catalog: {selected_line or runtime.get('backend')}")
            print("\nObservability:")
            print(f"- total_events: {metrics.get('total_events', 0)}")
            print(f"- avg_latency_ms: {metrics.get('avg_latency_ms', 0)}")
            print(f"- fallback_count: {metrics.get('fallback_count', 0)}")
            print(f"- error_count: {metrics.get('error_count', 0)}")
            print(f"- gpu_devices: {len(gpu.get('devices', []))}")
            if analysis_metrics:
                print(f"- analysis_total_events: {analysis_metrics.get('total_events', 0)}")
                print(f"- schema_valid_rate: {analysis_metrics.get('schema_valid_rate', 0)}")
                print(f"- analysis_error_count: {analysis_metrics.get('error_count', 0)}")
            probe = status.get("probe")
            if probe:
                print("\nProbe:")
                print(f"- reachable: {probe.get('reachable')}")
                print(f"- latency_ms: {probe.get('latency_ms')}")
                print(f"- error: {probe.get('error') or '-'}")
            benchmark = status.get("concurrency_benchmark")
            if benchmark:
                print("\nConcurrency Benchmark:")
                print(f"- requested_concurrency: {benchmark.get('requested_concurrency')}")
                print(f"- allowed_count: {benchmark.get('allowed_count')}")
                print(f"- blocked_count: {benchmark.get('blocked_count')}")
                print(f"- blocked_reasons: {benchmark.get('blocked_reasons')}")
                print(f"- total_elapsed_ms: {benchmark.get('total_elapsed_ms')}")
            streaming = status.get("streaming")
            if streaming:
                print("\nStreaming:")
                print(f"- api_streaming_supported: {streaming.get('api_streaming_supported')}")
                print(f"- notes: {streaming.get('notes')}")
            if safety:
                print("\nSafety:")
                print(f"- log_redaction_enabled: {safety.get('log_redaction_enabled')}")
                print(f"- prompt_audit_enabled: {safety.get('prompt_audit_enabled')}")
                print(f"- prompt_preview_chars: {safety.get('prompt_preview_chars')}")
            if features:
                print("\nFeatures:")
                for name in sorted(features):
                    print(f"- {name}: {features.get(name)}")
        return 0

    if args.command == "configure":
        from socc.cli.installer import runtime_home
        from socc.utils.config_loader import (
            batch_update_env,
            read_all_env,
            remove_env_assignment,
            runtime_env_path,
            update_env_assignment,
        )

        home = _runtime_home_arg(args.home)
        env_path = runtime_home(home) / ".env"

        if args.configure_command == "show":
            values = read_all_env(env_path)
            if args.json:
                # redact secrets in JSON output
                redacted = {}
                for k, v in values.items():
                    upper = k.upper()
                    if any(tok in upper for tok in ("KEY", "TOKEN", "PASS", "SECRET", "PASSWORD", "BEARER")):
                        redacted[k] = v[:4] + "****" if len(v) > 4 else "****"
                    else:
                        redacted[k] = v
                print(json.dumps(redacted, indent=2, ensure_ascii=False))
            else:
                print("Configuração ativa:")
                for k, v in sorted(values.items()):
                    upper = k.upper()
                    if any(tok in upper for tok in ("KEY", "TOKEN", "PASS", "SECRET", "PASSWORD", "BEARER")):
                        display = v[:4] + "****" if len(v) > 4 else "****"
                    else:
                        display = v
                    print(f"  {k}={display}")
            return 0

        if args.configure_command == "set":
            update_env_assignment(env_path, args.key, args.value)
            payload = {"updated": True, "key": args.key, "path": str(env_path)}
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print(f"  OK: {args.key} atualizado em {env_path}")
            return 0

        if args.configure_command == "unset":
            remove_env_assignment(env_path, args.key)
            payload = {"removed": True, "key": args.key, "path": str(env_path)}
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print(f"  OK: {args.key} comentado em {env_path}")
            return 0

        if args.configure_command == "validate":
            values = read_all_env(env_path)
            issues: list[dict[str, str]] = []
            # Basic validation rules
            url_keys = [k for k in values if "URL" in k.upper()]
            for k in url_keys:
                v = values[k]
                if v and not (v.startswith("http://") or v.startswith("https://")):
                    issues.append({"key": k, "issue": f"Value '{v}' does not look like a URL"})
            bool_keys = [k for k in values if k.upper().startswith("SOCC_FEATURE_") or "ENABLED" in k.upper()]
            for k in bool_keys:
                v = values[k].lower()
                if v not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
                    issues.append({"key": k, "issue": f"Value '{values[k]}' is not a valid boolean"})
            payload = {"valid": len(issues) == 0, "issues": issues, "keys_checked": len(values)}
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                if issues:
                    print(f"Validação: {len(issues)} problema(s) encontrado(s)")
                    for item in issues:
                        print(f"  - {item['key']}: {item['issue']}")
                else:
                    print(f"  OK: {len(values)} chaves validadas sem problemas.")
            return 0

    if args.command == "models":
        from socc.gateway.llm_gateway import list_backend_models, probe_inference_backend, runtime_status
        from socc.utils.config_loader import runtime_env_path, update_env_assignment

        if args.models_command == "list":
            try:
                models_data = list_backend_models()
            except Exception as exc:
                models_data = {"models": [], "error": str(exc)}
            if args.json:
                print(json.dumps(models_data, indent=2, ensure_ascii=False))
            else:
                models = models_data.get("models", [])
                if models:
                    print(f"Modelos disponíveis ({len(models)}):")
                    for m in models:
                        if isinstance(m, dict):
                            print(f"  - {m.get('name', m.get('model', '?'))}")
                        else:
                            print(f"  - {m}")
                else:
                    print("Nenhum modelo encontrado.")
                    if models_data.get("error"):
                        print(f"  Erro: {models_data['error']}")
            return 0

        if args.models_command == "set":
            env_path = runtime_env_path()
            if args.fast:
                key = "SOCC_OLLAMA_FAST_MODEL"
            elif args.balanced:
                key = "SOCC_OLLAMA_BALANCED_MODEL"
            else:
                key = "SOCC_OLLAMA_DEEP_MODEL"
            update_env_assignment(env_path, key, args.model)
            profile = "fast" if args.fast else ("balanced" if args.balanced else "deep")
            payload = {"updated": True, "profile": profile, "model": args.model}
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print(f"  OK: Perfil {profile} → {args.model}")
            return 0

        if args.models_command == "fallback":
            from socc.utils.config_loader import read_env_value, remove_env_assignment, update_env_assignment

            env_path = runtime_env_path()

            if args.fallback_command == "list":
                current = os.environ.get("SOCC_LLM_FALLBACK_PROVIDER", "")
                if not current:
                    current = read_env_value(env_path, "SOCC_LLM_FALLBACK_PROVIDER") or ""
                priority = os.environ.get("SOCC_BACKEND_PRIORITY", "")
                if not priority:
                    priority = read_env_value(env_path, "SOCC_BACKEND_PRIORITY") or ""
                payload = {
                    "fallback_provider": current or "(não configurado)",
                    "backend_priority": priority or "(não configurado)",
                }
                if args.json:
                    print(json.dumps(payload, indent=2, ensure_ascii=False))
                else:
                    print("Fallback:")
                    print(f"  - provider: {payload['fallback_provider']}")
                    print(f"  - backend_priority: {payload['backend_priority']}")
                return 0

            if args.fallback_command == "add":
                valid = {"anthropic", "ollama", "lmstudio", "vllm", "openai-compatible", "cpu", "deterministic"}
                provider = args.provider.lower()
                if provider not in valid:
                    print(f"  ERRO: Provider '{provider}' inválido. Opções: {', '.join(sorted(valid))}")
                    return 1
                update_env_assignment(env_path, "SOCC_LLM_FALLBACK_PROVIDER", provider)
                payload = {"updated": True, "fallback_provider": provider}
                if args.json:
                    print(json.dumps(payload, indent=2, ensure_ascii=False))
                else:
                    print(f"  OK: Fallback definido como '{provider}'")
                return 0

            if args.fallback_command == "remove":
                remove_env_assignment(env_path, "SOCC_LLM_FALLBACK_PROVIDER")
                payload = {"removed": True}
                if args.json:
                    print(json.dumps(payload, indent=2, ensure_ascii=False))
                else:
                    print("  OK: Fallback provider removido.")
                return 0

        if args.models_command == "test":
            probe = probe_inference_backend()
            payload = {
                "reachable": probe.get("reachable", False),
                "latency_ms": probe.get("latency_ms"),
                "error": probe.get("error"),
            }
            if args.model:
                payload["model_tested"] = args.model
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                if probe.get("reachable"):
                    print(f"  OK: Backend acessível (latência: {probe.get('latency_ms', '?')} ms)")
                else:
                    print(f"  ERRO: Backend inacessível — {probe.get('error', 'desconhecido')}")
            return 0

    if args.command == "vantage":
        from socc.core.engine import (
            vantage_modules_payload,
            vantage_probe_payload,
            vantage_status_payload,
        )

        if args.vantage_command == "status":
            payload = vantage_status_payload()
        elif args.vantage_command == "modules":
            payload = vantage_modules_payload()
        else:
            payload = vantage_probe_payload(args.module)

        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        elif args.vantage_command == "probe":
            print(f"module: {payload.get('module')}")
            print(f"ok: {payload.get('ok')}")
            print(f"status_code: {payload.get('status_code')}")
            print(f"error: {payload.get('error') or '-'}")
        else:
            print("Vantage:")
            print(f"- enabled: {payload.get('enabled')}")
            print(f"- base_url: {payload.get('base_url') or '-'}")
            print(f"- auth_mode: {payload.get('auth_mode')}")
            if args.vantage_command == "modules":
                print(f"- selected_modules: {', '.join(payload.get('selected_modules', [])) or '-'}")
                for item in payload.get("modules", []):
                    if not isinstance(item, dict):
                        continue
                    print(
                        f"  - {item.get('id')}: {item.get('path')} "
                        f"(selected={item.get('selected')})"
                    )
        return 0

    if args.command == "analyze":
        from socc.core.engine import analyze_payload

        payload = _read_payload(args)
        result = analyze_payload(
            payload_text=payload,
            cliente=args.cliente,
            regra=args.regra,
            classificacao=args.classificacao,
            include_draft=not args.no_draft,
        )
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("Campos normalizados:")
            print(json.dumps(result["fields"], indent=2, ensure_ascii=False))
            structured = result.get("analysis_structured") or {}
            if structured:
                print("\nAnálise estruturada oficial:")
                print(f"- summary: {structured.get('summary', '')}")
                print(f"- verdict: {structured.get('verdict', '')}")
                print(f"- confidence: {structured.get('confidence', 0)}")
            trace = result.get("analysis_trace") or {}
            if trace:
                print(f"- observed_facts: {len(trace.get('observed_facts', []))}")
                print(f"- inferences: {len(trace.get('inferences', []))}")
                print(f"- limitations: {len(trace.get('limitations', []))}")
            if "draft" in result:
                print("\nDraft:")
                print(result["draft"])
        return 0

    if args.command == "tui":
        from socc.cli.chat_interactive import run_chat_tui
        return run_chat_tui(
            session_id=getattr(args, "session_id", "") or "",
            cliente=getattr(args, "cliente", "") or "",
            response_mode=getattr(args, "response_mode", "balanced"),
            selected_backend=getattr(args, "backend", "") or "",
            selected_model=getattr(args, "model", "") or "",
            stream=True,
        )

    if args.command == "chat":
        from socc.core.engine import chat_reply, stream_chat_events

        if _chat_requires_interactive(args):
            return _run_interactive_chat(args)

        message = _read_chat_message(args)
        if args.json:
            result = chat_reply(
                message=message,
                session_id=args.session_id,
                cliente=args.cliente,
                response_mode=args.response_mode,
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.stream:
            final_payload: dict[str, object] | None = None
            for event in stream_chat_events(
                message=message,
                session_id=args.session_id,
                cliente=args.cliente,
                response_mode=args.response_mode,
            ):
                if event.get("event") == "delta":
                    print(str(event.get("delta") or ""), end="", flush=True)
                elif event.get("event") == "final":
                    data = event.get("data")
                    if isinstance(data, dict):
                        final_payload = data
            print()
            if isinstance(final_payload, dict) and final_payload.get("type") == "error":
                print(final_payload.get("message") or "")
            return 0

        result = chat_reply(
            message=message,
            session_id=args.session_id,
            cliente=args.cliente,
            response_mode=args.response_mode,
        )
        print(f"Sessao: {result.get('session_id', args.session_id or 'default')}")
        print(f"Skill: {result.get('skill', '-') or '-'}")
        print()
        print(result.get("content") or result.get("message") or "")
        return 0

    if args.command == "intel":
        from socc.core.knowledge_base import ensure_knowledge_base, ingest_source, inspect_index, register_source

        runtime_override = Path(args.home).expanduser() if getattr(args, "home", None) else None
        ensure_knowledge_base(runtime_override)

        if args.intel_command == "list":
            payload = inspect_index(runtime_override)
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                manifest = payload.get("manifest", {})
                print("Knowledge Base:")
                print(f"- index_version: {manifest.get('version')}")
                print(f"- indexed_documents: {manifest.get('indexed_documents', 0)}")
                print(f"- indexed_chunks: {manifest.get('indexed_chunks', 0)}")
                print(f"- chunk_chars: {manifest.get('chunk_chars')}")
                print(f"- chunk_overlap: {manifest.get('chunk_overlap')}")
                print("\nSources:")
                for source in payload.get("sources", []):
                    print(
                        f"- {source.get('id')}: {source.get('name')} "
                        f"(docs={source.get('documents', 0)} chunks={source.get('chunks', 0)} trust={source.get('trust')})"
                    )
            return 0

        if args.intel_command == "add-source":
            payload = register_source(
                source_id=args.id,
                name=args.name,
                kind=args.kind,
                trust=args.trust,
                path=args.path,
                tags=[item.strip() for item in str(args.tags or "").split(",") if item.strip()],
                description=args.description,
                home=runtime_override,
            )
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                source = payload.get("source", {})
                print(f"Source {'created' if payload.get('created') else 'updated'}:")
                print(f"- id: {source.get('id')}")
                print(f"- name: {source.get('name')}")
                print(f"- path: {source.get('path') or '-'}")
                print(f"- tags: {', '.join(source.get('tags', [])) or '-'}")
            return 0

        if args.intel_command == "ingest":
            payload = ingest_source(
                source_id=args.source_id,
                input_path=args.path or None,
                home=runtime_override,
            )
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print("Ingestão concluída:")
                print(f"- source_id: {(payload.get('source') or {}).get('id')}")
                print(f"- documents_indexed: {payload.get('documents_indexed', 0)}")
                print(f"- chunks_indexed: {payload.get('chunks_indexed', 0)}")
                print(f"- index_path: {payload.get('index_path')}")
            return 0

    if args.command == "train":
        from socc.core.training_engine import TrainingEngine, default_engine

        home_override = _runtime_home_arg(getattr(args, "home", None))

        if getattr(args, "training_dir", ""):
            engine = TrainingEngine(training_dir=args.training_dir)
        else:
            engine = default_engine(home_override)

        # --- status ---
        if getattr(args, "status", False):
            payload = engine.status()
            if getattr(args, "json", False):
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print("Training Engine:")
                print(f"  modelo_treinado    : {payload['model_available']}")
                print(f"  modelo_desatualizado: {payload['model_stale']}")
                print(f"  amostras           : {payload['n_samples']}")
                print(f"  treinado_em        : {payload.get('trained_at') or '-'}")
                print(f"  diretório_training : {payload['training_dir']}")
                print(f"  distribuição:")
                for label, count in (payload.get("label_distribution") or {}).items():
                    print(f"    - {label}: {count}")
            return 0

        # --- list ---
        if getattr(args, "list", False):
            records = engine.list_training_records()
            if getattr(args, "json", False):
                print(json.dumps(records, indent=2, ensure_ascii=False))
            else:
                print(f"Casos de treinamento ({len(records)}):")
                for rec in records:
                    print(
                        f"  [{rec['classificacao'][:3].upper():3}] "
                        f"Ofensa {rec['ofensa_id']:8} | {rec['cliente']:20} | {rec['tipo_alerta'][:60]}"
                    )
            return 0

        # --- predict ---
        predict_text = getattr(args, "predict", "") or ""
        predict_file = getattr(args, "predict_file", "") or ""
        if predict_file:
            predict_text = Path(predict_file).read_text(encoding="utf-8", errors="replace")

        if predict_text:
            if engine.is_stale():
                print("Modelo desatualizado. Retreinando antes da inferência...")
                engine.train(force=True)
            payload = engine.predict(predict_text)
            if getattr(args, "json", False):
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                if not payload.get("model_available"):
                    print(f"  Erro: {payload.get('message')}")
                    return 1
                print(f"  Classificação prevista : {payload['predicted_classification']}")
                print(f"  Confiança              : {payload['confidence'] * 100:.0f}%")
                print(f"  Casos similares:")
                for case in payload.get("similar_cases", []):
                    print(
                        f"    - Ofensa {case['ofensa_id']:8} ({case['cliente']}) "
                        f"[{case['classificacao']}] {case['similaridade'] * 100:.0f}%"
                    )
                hints = payload.get("reasoning_hints", [])
                if hints:
                    print(f"  Dicas de raciocínio:")
                    for hint in hints:
                        print(f"    • {hint}")
            return 0

        # --- train (default) ---
        payload = engine.train(force=getattr(args, "force", False))
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            status = payload.get("status", "?")
            if status == "ok":
                print("Modelo treinado com sucesso:")
                print(f"  amostras    : {payload['n_samples']}")
                print(f"  k_neighbors : {payload['k_neighbors']}")
                print(f"  distribuição:")
                for label, count in (payload.get("label_distribution") or {}).items():
                    print(f"    - {label}: {count}")
                print(f"  modelo salvo em: {payload.get('model_path')}")
            elif status == "skipped":
                print(f"  Nenhuma ação necessária: {payload.get('reason')}")
                print("  Use --force para retreinar.")
            else:
                print(f"  Erro: {payload.get('reason')}")
                return 1
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
