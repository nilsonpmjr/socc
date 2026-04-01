"""
Subagent forking system for SOCC.

Creates specialised subagents that run tasks with restricted tool sets
and return structured results.

Attribution: Inspired by instructkr/claude-code AgentTool/forkSubagent.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from socc.core.harness.models import AgentResult, AgentSpecialty, SOCAgentSpec
from socc.core.tools_registry import invoke_tool

__all__ = [
    "SubagentConfig",
    "SubagentHandle",
    "fork_subagent",
    "get_subagent",
    "list_active_subagents",
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


@dataclass
class SubagentHandle:
    """Handle to a running or completed subagent."""

    id: str
    name: str
    status: str = "pending"  # pending, running, completed, failed, timeout
    result: AgentResult | None = None
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    @property
    def elapsed_seconds(self) -> float:
        end = self.completed_at or time.time()
        return end - self.started_at

    @property
    def is_done(self) -> bool:
        return self.status in ("completed", "failed", "timeout")


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
        status="pending",
    )

    with _lock:
        _registry[handle.id] = handle

    _logger.info(
        "Forking subagent %s (%s) for task: %s",
        handle.id, config.specialty, config.task[:80],
    )

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
            handle.completed_at = time.time()
            handle.result = AgentResult(
                ok=False,
                agent_name=config.specialty,
                conclusion=f"Subagent timed out after {config.timeout_seconds}s",
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
        # Resolve agent spec
        spec = _resolve_agent(config.specialty, agent_specs)

        # Filter tools
        allowed_tools = config.tools or (
            spec.tools_whitelist if spec else []
        )

        # Build prompt
        prompt = _build_prompt(config, spec)

        # Execute reasoning steps
        findings: list[str] = []
        reasoning: list[str] = []

        reasoning.append(f"[step 0] Received task: {config.task}")

        # Step 1: Extract IOCs if text context provided
        if "text" in config.context and "extract_iocs" in allowed_tools:
            ioc_result = invoke_tool("extract_iocs", {"text": config.context["text"]})
            if ioc_result.ok and ioc_result.output:
                for ioc_type, values in ioc_result.output.items():
                    if values:
                        findings.append(f"Found {len(values)} {ioc_type}: {values[:5]}")
                reasoning.append(f"[step 1] Extracted IOCs: {len(findings)} findings")

        # LLM synthesis — call the same gateway the chat uses
        llm_content = ""
        try:
            from socc.core.chat import generate_chat_reply
            llm_result = generate_chat_reply(
                message=prompt,
                session_id=f"subagent-{handle.id}",
                response_mode="fast",   # lightweight — subagents use fast model
            )
            llm_content = str(llm_result.get("content") or "").strip()
            if llm_content:
                import re as _re
                bullet_findings = _re.findall(
                    r"^[\s]*[-*\u2022]\s+(.+)$", llm_content, _re.MULTILINE
                )
                if bullet_findings:
                    findings.extend(bullet_findings)
                elif not findings:
                    # no bullets — use first 200 chars as single finding
                    findings.append(llm_content[:200])
                reasoning.append(f"[llm] {len(bullet_findings)} findings from LLM response")
            else:
                reasoning.append("[llm] empty response — using deterministic findings only")
        except Exception as _llm_exc:
            _logger.warning("fork_subagent LLM call failed: %s", _llm_exc)
            reasoning.append(f"[llm] failed ({type(_llm_exc).__name__}) — deterministic only")

        handle.result = AgentResult(
            ok=True,
            agent_name=config.specialty,
            conclusion=f"Analysis of '{config.task[:50]}' complete with {len(findings)} findings",
            findings=findings,
            reasoning_trace=reasoning,
            elapsed_seconds=time.time() - start,
        )
        handle.status = "completed"

    except Exception as exc:
        _logger.exception("Subagent %s failed", handle.id)
        handle.result = AgentResult(
            ok=False,
            agent_name=config.specialty,
            conclusion=f"Error: {type(exc).__name__}: {exc}",
            elapsed_seconds=time.time() - start,
        )
        handle.status = "failed"

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
