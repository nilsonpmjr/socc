"""Subagent execution helpers for the harness runtime."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from socc.core.harness.models import AgentResult, SOCAgentSpec
from socc.core.tools_registry import ToolResult, invoke_tool

__all__ = [
    "SubagentConfig",
    "SubagentHandle",
    "fork_subagent",
    "get_subagent",
    "list_active_subagents",
    "list_all_subagents",
]

_logger = logging.getLogger(__name__)


@dataclass
class SubagentConfig:
    """Configuration for forking a subagent."""

    name: str
    specialty: str  # AgentSpecialty value or agent name
    task: str
    context: dict[str, Any] = field(default_factory=dict)
    tools: list[str] = field(default_factory=list)
    max_steps: int = 10
    timeout_seconds: int = 300
    parent_id: str | None = None
    task_id: str = ""


@dataclass
class SubagentHandle:
    """Handle to a running or completed subagent."""

    id: str
    name: str
    specialty: str = ""
    task_id: str = ""
    status: str = "pending"  # pending, running, completed, failed, timeout
    result: AgentResult | None = None
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    error_kind: str = ""
    resolved_tools: list[str] = field(default_factory=list)

    @property
    def elapsed_seconds(self) -> float:
        end = self.completed_at or time.time()
        return end - self.started_at

    @property
    def is_done(self) -> bool:
        return self.status in ("completed", "failed", "timeout")

    def to_dict(self) -> dict[str, Any]:
        result = self.result
        metadata = result.metadata if result is not None else {}
        return {
            "id": self.id,
            "name": self.name,
            "specialty": self.specialty,
            "task_id": self.task_id,
            "status": self.status,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "error_kind": self.error_kind or (result.error_kind if result else ""),
            "summary": result.conclusion if result is not None else "",
            "resolved_tools": list(self.resolved_tools or metadata.get("allowed_tools") or []),
        }


# ── Registry ──────────────────────────────────────────────────────────────

_registry: dict[str, SubagentHandle] = {}
_lock = threading.Lock()


def fork_subagent(
    config: SubagentConfig,
    agent_specs: dict[str, SOCAgentSpec] | None = None,
    *,
    block: bool = True,
) -> SubagentHandle:
    """Create and start a subagent.

    Args:
        config: Subagent configuration.
        agent_specs: Available agent specs (if None, uses RUNTIME).
        block: Wait for completion (True) or return immediately (False).

    Returns:
        Handle for tracking the subagent.
    """
    handle = SubagentHandle(
        id=uuid.uuid4().hex[:8],
        name=config.name,
        specialty=config.specialty,
        task_id=config.task_id,
        status="pending",
    )

    with _lock:
        _registry[handle.id] = handle

    if config.task_id:
        try:
            from socc.core import task_state

            task_state.attach_subagent(config.task_id, handle.id)
        except Exception:
            pass

    _logger.info("Forking subagent %s (%s)", handle.id, config.specialty)

    thread = threading.Thread(
        target=_run_subagent,
        args=(handle, config, agent_specs),
        daemon=True,
        name=f"subagent-{handle.id}",
    )
    thread.start()

    if block:
        thread.join(timeout=config.timeout_seconds)
        if thread.is_alive():
            handle.status = "timeout"
            handle.error_kind = "timeout"
            handle.completed_at = time.time()
            handle.result = AgentResult(
                ok=False,
                agent_name=config.specialty,
                conclusion=f"Subagent timed out after {config.timeout_seconds}s",
                error_kind="timeout",
            )
            _logger.warning("Subagent %s timed out", handle.id)

    return handle


def _run_subagent(
    handle: SubagentHandle,
    config: SubagentConfig,
    agent_specs: dict[str, SOCAgentSpec] | None,
) -> None:
    """Execute subagent task (internal thread target)."""
    handle.status = "running"
    start = time.time()

    try:
        spec = _resolve_agent(config.specialty, agent_specs)
        allowed_tools = _resolve_allowed_tools(config, spec)
        handle.resolved_tools = list(allowed_tools)
        prompt = _build_prompt(config, spec)

        findings: list[str] = []
        reasoning: list[str] = []
        tool_calls: list[ToolResult] = []
        tool_errors: list[str] = []
        llm_error = ""

        reasoning.append(f"[step 0] Task accepted: {config.task}")
        reasoning.append(
            f"[policy] allowed tools: {', '.join(allowed_tools) if allowed_tools else '(none)'}"
        )

        if "text" in config.context and "extract_iocs" in allowed_tools:
            ioc_result = _invoke_allowed_tool(
                "extract_iocs",
                {"text": config.context["text"]},
                allowed_tools=allowed_tools,
                tool_calls=tool_calls,
            )
            if ioc_result.ok and ioc_result.output:
                for ioc_type, values in ioc_result.output.items():
                    if values:
                        findings.append(f"Found {len(values)} {ioc_type}: {values[:5]}")
                reasoning.append(f"[step 1] deterministic IOC extraction yielded {len(findings)} findings")
            elif ioc_result.error:
                tool_errors.append(ioc_result.error)
                reasoning.append(f"[tool] extract_iocs failed: {ioc_result.error}")

        try:
            from socc.core.chat import generate_chat_reply

            llm_result = generate_chat_reply(
                message=prompt,
                session_id=f"subagent-{handle.id}",
                response_mode="fast",
            )
            llm_content = str(llm_result.get("content") or "").strip()
            llm_findings = _extract_findings(llm_content)
            if llm_findings:
                findings.extend(llm_findings)
                reasoning.append(f"[llm] merged {len(llm_findings)} findings from model output")
            else:
                reasoning.append("[llm] empty response, deterministic findings kept")
        except Exception as _llm_exc:
            llm_error = f"{type(_llm_exc).__name__}: {_llm_exc}"
            _logger.warning("fork_subagent LLM call failed: %s", llm_error)
            reasoning.append(f"[llm] failed ({type(_llm_exc).__name__}) — falling back to deterministic path")

        error_kind = ""
        ok = True
        if not findings and tool_errors:
            ok = False
            error_kind = "tool_error"
        elif not findings and llm_error and not tool_calls:
            ok = False
            error_kind = "llm_error"

        metadata = {
            "allowed_tools": allowed_tools,
            "tool_errors": tool_errors,
            "llm_error": llm_error,
            "max_steps": config.max_steps,
            "timeout_seconds": config.timeout_seconds,
        }

        handle.result = AgentResult(
            ok=ok,
            agent_name=config.specialty,
            conclusion=_build_conclusion(config.task, findings, error_kind),
            findings=findings,
            tool_calls=tool_calls,
            reasoning_trace=reasoning,
            elapsed_seconds=time.time() - start,
            error_kind=error_kind,
            metadata=metadata,
        )
        handle.status = "completed" if ok else "failed"
        handle.error_kind = error_kind

    except Exception as exc:
        _logger.exception("Subagent %s failed", handle.id)
        handle.result = AgentResult(
            ok=False,
            agent_name=config.specialty,
            conclusion=f"Error: {type(exc).__name__}: {exc}",
            elapsed_seconds=time.time() - start,
            error_kind="runtime_error",
        )
        handle.status = "failed"
        handle.error_kind = "runtime_error"

    finally:
        handle.completed_at = time.time()


def _resolve_agent(
    specialty: str,
    specs: dict[str, SOCAgentSpec] | None,
) -> SOCAgentSpec | None:
    """Resolve an agent spec by name or specialty."""
    if specs:
        if specialty in specs:
            return specs[specialty]
        for spec in specs.values():
            if spec.specialty.value == specialty:
                return spec

    # Try runtime
    try:
        from socc.core.harness.runtime import RUNTIME
        return RUNTIME.get_agent(specialty)
    except ImportError:
        return None


def _resolve_allowed_tools(
    config: SubagentConfig,
    spec: SOCAgentSpec | None,
) -> list[str]:
    requested = list(dict.fromkeys(config.tools))
    if spec is None:
        return requested

    if spec.tools_whitelist:
        allowed = set(spec.tools_whitelist)
        if requested:
            allowed &= set(requested)
    else:
        allowed = set(requested)

    allowed -= set(spec.tools_blacklist)
    return sorted(allowed)


def _invoke_allowed_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    allowed_tools: list[str],
    tool_calls: list[ToolResult],
) -> ToolResult:
    if name not in allowed_tools:
        return ToolResult(
            ok=False,
            error=f"Tool '{name}' is not allowed for this subagent",
            arguments=arguments,
        )

    result = invoke_tool(name, arguments)
    tool_calls.append(result)
    return result


def _build_prompt(config: SubagentConfig, spec: SOCAgentSpec | None) -> str:
    """Build the prompt for a subagent."""
    parts = [f"# Task: {config.task}", ""]

    if spec:
        parts.extend([
            f"## Agent: {spec.name} ({spec.specialty.value})",
            spec.prompt_template if spec.prompt_template else "",
            "",
        ])

    if config.context:
        parts.append("## Context:")
        for key, value in config.context.items():
            val_str = str(value)
            if len(val_str) > 500:
                val_str = val_str[:500] + "..."
            parts.append(f"- **{key}**: {val_str}")
        parts.append("")

    if config.tools:
        parts.append(f"## Available Tools: {', '.join(config.tools)}")

    return "\n".join(parts)


def _extract_findings(content: str) -> list[str]:
    cleaned = content.strip()
    if not cleaned:
        return []
    import re as _re

    bullet_findings = _re.findall(r"^[\s]*[-*\u2022]\s+(.+)$", cleaned, _re.MULTILINE)
    if bullet_findings:
        return bullet_findings
    return [cleaned[:200]]


def _build_conclusion(task: str, findings: list[str], error_kind: str) -> str:
    if findings:
        return f"Analysis of '{task[:50]}' completed with {len(findings)} findings"
    if error_kind == "tool_error":
        return f"Analysis of '{task[:50]}' failed during deterministic tool execution"
    if error_kind == "llm_error":
        return f"Analysis of '{task[:50]}' produced no findings after LLM fallback"
    return f"Analysis of '{task[:50]}' completed"


# ── Queries ───────────────────────────────────────────────────────────────


def get_subagent(subagent_id: str) -> SubagentHandle | None:
    with _lock:
        return _registry.get(subagent_id)


def list_active_subagents() -> list[SubagentHandle]:
    with _lock:
        return [h for h in _registry.values() if not h.is_done]


def list_all_subagents(limit: int = 50) -> list[SubagentHandle]:
    with _lock:
        handles = sorted(_registry.values(), key=lambda h: h.started_at, reverse=True)
        return handles[:limit]
