from __future__ import annotations

from pathlib import Path

from soc_copilot.modules import parser_engine


def parse_text_payload(payload: str, raw_fields: dict | None = None) -> dict:
    return parser_engine.parse(raw_fields or {}, payload)


def parse_file(path: str | Path, raw_fields: dict | None = None) -> dict:
    payload = Path(path).read_text(encoding="utf-8", errors="replace")
    return parse_text_payload(payload, raw_fields=raw_fields)


def extract_iocs_from_file(path: str | Path) -> dict:
    payload = Path(path).read_text(encoding="utf-8", errors="replace")
    return parser_engine.extract_iocs(payload)
