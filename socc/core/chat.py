from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from soc_copilot.modules import chat_service


LEGACY_MODULE = "soc_copilot.modules.chat_service"


def select_skill(message: str, artifact_type: str | None = None) -> str:
    return chat_service.select_skill(message, artifact_type=artifact_type)


def generate_chat_reply(
    message: str,
    session_id: str = "",
    cliente: str = "",
) -> dict[str, Any]:
    return chat_service.generate_chat_reply(
        message=message,
        session_id=session_id,
        cliente=cliente,
    )


def stream_chat_reply_events(
    message: str,
    session_id: str = "",
    cliente: str = "",
) -> Iterator[dict[str, object]]:
    return chat_service.stream_chat_reply_events(
        message=message,
        session_id=session_id,
        cliente=cliente,
    )
