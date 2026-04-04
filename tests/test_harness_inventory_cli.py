from __future__ import annotations

import io
import subprocess
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def bootstrapped_runtime():
    import socc.cli.startup as startup_mod
    from socc.agents import fork as fork_mod
    from socc.core.harness.runtime import RUNTIME

    startup_mod._started = False
    fork_mod._registry.clear()
    RUNTIME._agents.clear()
    RUNTIME._agent_sources.clear()
    RUNTIME._tool_snapshots.clear()
    RUNTIME._command_snapshots.clear()
    RUNTIME._initialised = False

    startup_mod.startup(block=True)
    return RUNTIME


def test_runtime_inventory_merges_snapshot_and_live_records(bootstrapped_runtime):
    command_records = {
        record.name: record
        for record in bootstrapped_runtime.list_command_inventory(limit=100)
    }
    tool_records = {
        record.name: record
        for record in bootstrapped_runtime.list_tool_inventory(limit=100)
    }

    assert command_records["case"].available is True
    assert command_records["report"].available is False
    assert command_records["report"].status.value == "planned"
    assert tool_records["bash"].available is True
    assert tool_records["bash"].category == "shell"


def test_route_prompt_prefers_live_command_matches(bootstrapped_runtime):
    matches = bootstrapped_runtime.route_prompt("list available agents", limit=5)
    assert matches
    assert matches[0].kind == "command"
    assert matches[0].name == "agents"
    assert matches[0].available is True


def test_route_prompt_scores_aliases_and_arguments(bootstrapped_runtime):
    matches = bootstrapped_runtime.route_prompt("r markdown", limit=5)
    assert matches
    assert any(match.kind == "command" and match.name == "report" for match in matches)


def test_route_prompt_prefers_live_items_on_snapshot_conflict(bootstrapped_runtime):
    from socc.core.harness.commands import COMMAND_REGISTRY

    live_description = COMMAND_REGISTRY.get("agents").description
    bootstrapped_runtime._command_snapshots["agents-legacy"] = {
        "name": "agents-legacy",
        "description": live_description,
        "aliases": [],
        "arguments": [
            {
                "name": "query",
                "type": "string",
                "required": False,
                "help": live_description,
            }
        ],
    }

    matches = bootstrapped_runtime.route_prompt(live_description, limit=5)
    assert matches
    assert matches[0].kind == "command"
    assert matches[0].name == "agents"
    assert matches[0].available is True
    assert any(match.name == "agents-legacy" and not match.available for match in matches)


def test_fork_subagent_records_tool_calls(bootstrapped_runtime):
    from socc.agents.fork import SubagentConfig, fork_subagent

    config = SubagentConfig(
        name="inventory-test",
        specialty="soc_analyst",
        task="inspect indicators",
        context={"text": "connect to 1.2.3.4 and evil.example"},
        tools=["extract_iocs"],
        timeout_seconds=30,
    )

    with patch("socc.core.chat.generate_chat_reply", return_value={"type": "message", "content": "", "session_id": "x"}):
        handle = fork_subagent(config, block=True)

    assert handle.result is not None
    assert handle.result.ok is True
    assert len(handle.result.tool_calls) == 1
    assert handle.result.tool_calls[0].ok is True


def test_fork_subagent_enforces_blacklist():
    from socc.agents.fork import SubagentConfig, fork_subagent
    from socc.core.harness.models import AgentSpecialty, SOCAgentSpec

    spec = SOCAgentSpec(
        name="locked_down",
        specialty=AgentSpecialty.GENERAL,
        description="test",
        prompt_template="test",
        tools_whitelist=["extract_iocs"],
        tools_blacklist=["extract_iocs"],
    )
    config = SubagentConfig(
        name="locked-test",
        specialty="locked_down",
        task="inspect indicators",
        context={"text": "evil.example"},
        tools=["extract_iocs"],
        timeout_seconds=30,
    )

    with patch("socc.core.chat.generate_chat_reply", return_value={"type": "message", "content": "", "session_id": "x"}):
        handle = fork_subagent(config, agent_specs={"locked_down": spec}, block=True)

    assert handle.result is not None
    assert handle.result.tool_calls == []
    assert handle.result.metadata["allowed_tools"] == []


def test_fork_subagent_block_false_exposes_lifecycle(bootstrapped_runtime):
    from socc.agents.fork import (
        SubagentConfig,
        fork_subagent,
        get_subagent,
        list_all_subagents,
    )

    config = SubagentConfig(
        name="async-test",
        specialty="soc_analyst",
        task="quick async run",
        context={},
        tools=[],
        timeout_seconds=30,
    )

    with patch("socc.core.chat.generate_chat_reply", return_value={"type": "message", "content": "- ready", "session_id": "x"}):
        handle = fork_subagent(config, block=False)

    assert get_subagent(handle.id) is handle

    deadline = time.time() + 2
    while not handle.is_done and time.time() < deadline:
        time.sleep(0.01)

    assert handle.is_done
    assert any(item.id == handle.id for item in list_all_subagents())


def test_cli_inventory_commands_work_without_pythonpath():
    result = subprocess.run(
        [sys.executable, "-m", "socc.cli.main", "commands", "--limit", "10"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "case" in result.stdout
    assert "report" in result.stdout


def test_cli_show_command_reports_snapshot_status():
    result = subprocess.run(
        [sys.executable, "-m", "socc.cli.main", "show-command", "report"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "planned" in result.stdout.lower()
    assert "hidden:" in result.stdout.lower()


def test_cli_show_tool_reports_auth_and_timeout():
    result = subprocess.run(
        [sys.executable, "-m", "socc.cli.main", "show-tool", "bash"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "requires_auth" in result.stdout
    assert "timeout_seconds" in result.stdout


def test_cli_agents_verbose_exposes_source_and_policy():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "socc.cli.main",
            "agents",
            "--query",
            "soc_analyst",
            "--verbose",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "source=" in result.stdout
    assert "tools=" in result.stdout


def test_subagents_cli_reports_lifecycle_and_error_kind(bootstrapped_runtime):
    from socc.agents.fork import SubagentConfig, fork_subagent
    from socc.cli.main import main

    def _slow_llm(*args, **kwargs):
        time.sleep(0.05)
        return {"type": "message", "content": "- ready", "session_id": "x"}

    config = SubagentConfig(
        name="cli-lifecycle-test",
        specialty="soc_analyst",
        task="track lifecycle",
        context={},
        tools=["extract_iocs"],
        timeout_seconds=30,
    )

    with patch("socc.core.chat.generate_chat_reply", side_effect=_slow_llm):
        handle = fork_subagent(config, block=False)

        deadline = time.time() + 1
        while handle.status == "pending" and time.time() < deadline:
            time.sleep(0.005)

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["subagents", "--active", "--json"])

    assert exit_code == 0
    active_payload = stdout.getvalue()
    assert '"status": "running"' in active_payload
    assert '"resolved_tools": [' in active_payload
    assert handle.id in active_payload

    deadline = time.time() + 1
    while not handle.is_done and time.time() < deadline:
        time.sleep(0.005)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = main(["subagents", "--json"])

    assert exit_code == 0
    payload = stdout.getvalue()
    assert handle.id in payload
    assert '"status": "completed"' in payload
    assert '"error_kind": ""' in payload
    assert '"summary": "Analysis of' in payload
