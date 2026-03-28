from __future__ import annotations

import json
from typing import Any


def sse_event(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def feature_disabled_payload(flag_name: str) -> dict[str, str]:
    return {
        "error": f"Feature '{flag_name}' desabilitada por configuracao.",
        "feature": flag_name,
    }
