from __future__ import annotations

from typing import Any

from soc_copilot.modules import parser_engine


LEGACY_MODULE = "soc_copilot.modules.parser_engine"


def parse_payload(payload_text: str, raw_fields: dict[str, Any] | None = None) -> dict[str, Any]:
    return parser_engine.parse(raw_fields or {}, payload_text)


def extract_iocs(text: str) -> dict[str, Any]:
    return parser_engine.extract_iocs(text)


def defang(text: str) -> str:
    return parser_engine.defang(text)
