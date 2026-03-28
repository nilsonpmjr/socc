from __future__ import annotations

from pathlib import Path

from socc.core import parser as parser_runtime


def parse_text_payload(payload: str, raw_fields: dict | None = None) -> dict:
    return parser_runtime.parse_payload(payload, raw_fields=raw_fields)


def parse_file(path: str | Path, raw_fields: dict | None = None) -> dict:
    payload = Path(path).read_text(encoding="utf-8", errors="replace")
    return parse_text_payload(payload, raw_fields=raw_fields)


def extract_iocs_from_file(path: str | Path) -> dict:
    payload = Path(path).read_text(encoding="utf-8", errors="replace")
    return parser_runtime.extract_iocs(payload)
