from __future__ import annotations

import base64
from typing import Any

from socc.core.contracts import ToolExecutionContract
from socc.core import parser as parser_runtime


def extract_iocs(text: str) -> dict:
    return parser_runtime.extract_iocs(text)


def defang(text: str) -> str:
    return parser_runtime.defang(text)


def decode_base64(value: str) -> str:
    raw = base64.b64decode(value)
    return raw.decode("utf-8", errors="replace")


TOOL_REGISTRY = {
    "extract_iocs": extract_iocs,
    "defang": defang,
    "decode_base64": decode_base64,
}


def list_tools() -> list[str]:
    return sorted(TOOL_REGISTRY)


def invoke_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = arguments or {}
    tool_fn = TOOL_REGISTRY.get(name)
    if tool_fn is None:
        return ToolExecutionContract(
            name=name,
            ok=False,
            arguments=payload,
            error="tool_not_found",
        ).to_dict()

    try:
        output = tool_fn(**payload)
    except Exception as exc:
        return ToolExecutionContract(
            name=name,
            ok=False,
            arguments=payload,
            error=str(exc),
        ).to_dict()

    return ToolExecutionContract(
        name=name,
        ok=True,
        arguments=payload,
        output=output,
    ).to_dict()
