from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


CONTRACT_VERSION = "1.0"


@dataclass(slots=True)
class ToolExecutionContract:
    name: str
    ok: bool
    arguments: dict[str, Any] = field(default_factory=dict)
    output: Any = None
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["contract_version"] = CONTRACT_VERSION
        return payload


@dataclass(slots=True)
class GatewayRequestContract:
    provider: str
    model: str
    messages: list[dict[str, str]] = field(default_factory=list)
    stream: bool = False
    tools: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["contract_version"] = CONTRACT_VERSION
        return payload


@dataclass(slots=True)
class GatewayResponseContract:
    provider: str
    model: str
    requested_device: str
    effective_device: str
    success: bool
    fallback_used: bool = False
    latency_ms: float = 0.0
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["contract_version"] = CONTRACT_VERSION
        return payload


@dataclass(slots=True)
class AnalysisEnvelope:
    fields: dict[str, Any]
    analysis: dict[str, Any]
    analysis_structured: dict[str, Any]
    analysis_priority: dict[str, Any]
    analysis_trace: dict[str, Any]
    analysis_schema_valid: bool
    runtime: dict[str, Any]
    rule_pack: dict[str, Any]
    gateway: dict[str, Any]
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    draft: str | None = None
    template_used: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["contract_version"] = CONTRACT_VERSION
        if self.draft is None:
            payload.pop("draft", None)
        if self.template_used is None:
            payload.pop("template_used", None)
        return payload


@dataclass(slots=True)
class ChatResponseEnvelope:
    response_type: str
    session_id: str
    skill: str
    runtime: dict[str, Any]
    gateway: dict[str, Any]
    content: str = ""
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "contract_version": CONTRACT_VERSION,
            "type": self.response_type,
            "session_id": self.session_id,
            "skill": self.skill,
            "content": self.content,
            "runtime": self.runtime,
            "gateway": self.gateway,
        }
        if self.message:
            payload["message"] = self.message
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload
