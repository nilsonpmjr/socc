"""Tests for harness wiring (HW-001..005)."""
from __future__ import annotations
from unittest.mock import patch
import pytest


# ---------------------------------------------------------------------------
# HW-002 — register_builtin_agents
# ---------------------------------------------------------------------------

class TestRegisterBuiltinAgents:
    def setup_method(self):
        # Reset RUNTIME to a clean state for each test
        from socc.core.harness.runtime import RUNTIME
        RUNTIME._agents.clear()
        RUNTIME._initialised = False

    def test_registers_three_specs(self):
        from socc.agents import register_builtin_agents
        from socc.core.harness.runtime import RUNTIME
        register_builtin_agents()
        names = [a.name for a in RUNTIME.list_agents()]
        assert "soc_analyst" in names
        assert "ir_agent" in names
        assert "threat_hunter" in names

    def test_idempotent(self):
        from socc.agents import register_builtin_agents
        from socc.core.harness.runtime import RUNTIME
        register_builtin_agents()
        count = len(RUNTIME.list_agents())
        register_builtin_agents()  # second call
        assert len(RUNTIME.list_agents()) == count


# ---------------------------------------------------------------------------
# HW-003 — startup()
# ---------------------------------------------------------------------------

class TestStartup:
    def test_blocking_startup(self):
        import socc.cli.startup as _mod
        _mod._started = False  # reset singleton
        from socc.cli.startup import startup
        startup(block=True)
        from socc.core.harness.commands import COMMAND_REGISTRY
        assert "case" in COMMAND_REGISTRY.list_names()
        assert "hunt" in COMMAND_REGISTRY.list_names()
        assert "tools" in COMMAND_REGISTRY.list_names()
        assert "agents" in COMMAND_REGISTRY.list_names()

    def test_tools_registered_after_startup(self):
        import socc.cli.startup as _mod
        _mod._started = False
        from socc.cli.startup import startup
        startup(block=True)
        from socc.core.tools_registry import list_tools
        tools = list_tools()
        assert "bash" in tools
        assert "extract_iocs" in tools
        assert "read" in tools

    def test_idempotent(self):
        import socc.cli.startup as _mod
        _mod._started = False
        from socc.cli.startup import startup
        startup(block=True)
        from socc.core.harness.commands import COMMAND_REGISTRY
        names_before = set(COMMAND_REGISTRY.list_names())
        startup(block=True)
        assert set(COMMAND_REGISTRY.list_names()) == names_before


# ---------------------------------------------------------------------------
# HW-004 — command dispatch
# ---------------------------------------------------------------------------

class TestCommandDispatch:
    def setup_method(self):
        import socc.cli.startup as _mod
        _mod._started = False
        from socc.cli.startup import startup
        startup(block=True)

    def test_tools_command(self):
        from socc.core.harness.commands import COMMAND_REGISTRY
        result = COMMAND_REGISTRY.dispatch("/tools")
        assert result.ok
        assert "bash" in result.output

    def test_agents_command(self):
        from socc.core.harness.commands import COMMAND_REGISTRY
        result = COMMAND_REGISTRY.dispatch("/agents")
        assert result.ok
        assert "soc_analyst" in result.output

    def test_help_command(self):
        from socc.core.harness.commands import COMMAND_REGISTRY
        result = COMMAND_REGISTRY.dispatch("/help")
        assert result.ok
        assert "/case" in result.output

    def test_case_create(self, tmp_path):
        from socc.core.harness.commands import COMMAND_REGISTRY
        from socc.cli.commands.case import CaseManager
        mgr = CaseManager(cases_dir=tmp_path)
        result = COMMAND_REGISTRY.dispatch("/case create Phishing-Test")
        assert result.ok
        assert "Phishing" in result.output or "case" in result.output.lower()

    def test_unknown_command_error(self):
        from socc.core.harness.commands import COMMAND_REGISTRY
        result = COMMAND_REGISTRY.dispatch("/nonexistent_xyz")
        assert not result.ok
        assert "Unknown command" in result.error or "nonexistent" in result.error


# ---------------------------------------------------------------------------
# HW-005 — fork_subagent with LLM
# ---------------------------------------------------------------------------

class TestForkSubagent:
    def setup_method(self):
        import socc.cli.startup as _mod
        _mod._started = False
        from socc.cli.startup import startup
        startup(block=True)

    def test_deterministic_ioc_extraction(self):
        from socc.agents.fork import fork_subagent, SubagentConfig
        config = SubagentConfig(
            name="test",
            specialty="soc_analyst",
            task="analyse suspicious IP",
            context={"text": "traffic to 1.2.3.4 and evil.com"},
            tools=["extract_iocs"],
            timeout_seconds=30,
        )
        mock_llm = {"type": "message", "content": "", "session_id": "x"}
        with patch("socc.core.chat.generate_chat_reply", return_value=mock_llm):
            handle = fork_subagent(config, block=True)
        assert handle.status == "completed"
        assert handle.result.ok
        ioc_findings = [f for f in handle.result.findings if "1.2.3.4" in f or "evil.com" in f]
        assert ioc_findings

    def test_llm_findings_merged(self):
        from socc.agents.fork import fork_subagent, SubagentConfig
        config = SubagentConfig(
            name="test",
            specialty="soc_analyst",
            task="analyse payload",
            context={},
            tools=[],
            timeout_seconds=30,
        )
        mock_llm = {
            "type": "message",
            "content": "- Finding A: malicious\n- Finding B: C2 communication",
            "session_id": "x",
        }
        with patch("socc.core.chat.generate_chat_reply", return_value=mock_llm):
            handle = fork_subagent(config, block=True)
        assert handle.status == "completed"
        assert handle.result.ok
        assert any("Finding A" in f for f in handle.result.findings)
        assert any("Finding B" in f for f in handle.result.findings)

    def test_llm_failure_fallback(self):
        from socc.agents.fork import fork_subagent, SubagentConfig
        config = SubagentConfig(
            name="test",
            specialty="soc_analyst",
            task="analyse payload",
            context={"text": "hash abc123"},
            tools=["extract_iocs"],
            timeout_seconds=30,
        )
        with patch("socc.core.chat.generate_chat_reply", side_effect=RuntimeError("LLM down")):
            handle = fork_subagent(config, block=True)
        # Should complete (deterministic) even if LLM fails
        assert handle.status == "completed"
        assert handle.result.ok
        assert any("llm" in t.lower() and "failed" in t.lower()
                   for t in handle.result.reasoning_trace)
