from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from socc.cli.installer import bootstrap_runtime


def _read_payload(args: argparse.Namespace) -> str:
    if args.text:
        return args.text
    if args.file:
        return Path(args.file).read_text(encoding="utf-8", errors="replace")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("Provide --file, --text, or pipe a payload to stdin.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="socc", description="SOCC local runtime CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create ~/.socc and seed local runtime files")
    init_parser.add_argument("--home", help="Alternative runtime home directory")
    init_parser.add_argument("--force", action="store_true", help="Overwrite generated runtime files")

    serve_parser = subparsers.add_parser("serve", help="Start the current SOCC web application")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    serve_parser.add_argument("--port", type=int, help="Bind port override")
    serve_parser.add_argument("--reload", action="store_true", help="Enable autoreload")
    serve_parser.add_argument("--log-level", default="info", help="Uvicorn log level")

    analyze_parser = subparsers.add_parser("analyze", help="Parse a payload and optionally draft an output")
    analyze_parser.add_argument("--file", help="Payload file to analyze")
    analyze_parser.add_argument("--text", help="Inline payload text")
    analyze_parser.add_argument("--cliente", default="", help="Client name for model selection")
    analyze_parser.add_argument("--regra", default="", help="Rule context for model selection")
    analyze_parser.add_argument("--classificacao", default="TP", help="Draft classification")
    analyze_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    analyze_parser.add_argument("--no-draft", action="store_true", help="Skip draft generation")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        result = bootstrap_runtime(Path(args.home).expanduser() if args.home else None, force=args.force)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "serve":
        from socc.core.engine import serve

        serve(host=args.host, port=args.port, reload=args.reload, log_level=args.log_level)
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
            if "draft" in result:
                print("\nDraft:")
                print(result["draft"])
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
