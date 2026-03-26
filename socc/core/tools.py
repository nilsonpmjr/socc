from __future__ import annotations

import base64

from soc_copilot.modules import parser_engine


def extract_iocs(text: str) -> dict:
    return parser_engine.extract_iocs(text)


def defang(text: str) -> str:
    return parser_engine.defang(text)


def decode_base64(value: str) -> str:
    raw = base64.b64decode(value)
    return raw.decode("utf-8", errors="replace")
