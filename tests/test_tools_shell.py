"""
Tests for socc/tools/shell.py — bash tool with timeout, blocklist, and redaction.
"""
from __future__ import annotations

import pytest

from socc.core.tools_registry import clear_registry, invoke_tool, list_tools


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_registry():
    clear_registry()
    from socc.tools.shell import register_shell_tools
    register_shell_tools()
    yield
    clear_registry()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestBashRegistration:
    def test_registered(self):
        assert "bash" in list_tools()

    def test_spec_is_high_risk(self):
        from socc.core.tools_registry import get_tool, RiskLevel
        spec = get_tool("bash")
        assert spec is not None
        assert spec.risk_level == RiskLevel.HIGH


# ---------------------------------------------------------------------------
# Basic execution
# ---------------------------------------------------------------------------

class TestBashExecution:
    def test_simple_command(self):
        result = invoke_tool("bash", {"command": "echo hello"})
        assert result.ok
        assert "hello" in result.output["stdout"]
        assert result.output["exit_code"] == 0
        assert result.output["blocked"] is False
        assert result.output["timed_out"] is False

    def test_exit_code_propagated(self):
        result = invoke_tool("bash", {"command": "exit 42"})
        assert result.ok  # tool itself succeeded
        assert result.output["exit_code"] == 42

    def test_stderr_captured(self):
        result = invoke_tool("bash", {"command": "echo error >&2"})
        assert result.ok
        assert "error" in result.output["stderr"]

    def test_default_timeout_parameter(self):
        # Should succeed instantly (well under 30s)
        result = invoke_tool("bash", {"command": "echo fast"})
        assert result.ok

    def test_multiline_output(self):
        result = invoke_tool("bash", {"command": "printf 'a\\nb\\nc\\n'"})
        assert result.ok
        assert "a" in result.output["stdout"]
        assert "b" in result.output["stdout"]


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------

class TestBashTimeout:
    def test_command_times_out(self):
        result = invoke_tool("bash", {"command": "sleep 10", "timeout": 1})
        assert result.ok
        assert result.output["timed_out"] is True
        assert result.output["exit_code"] == -1

    def test_timeout_capped_at_120(self):
        # Should not raise, just cap silently
        result = invoke_tool("bash", {"command": "echo fast", "timeout": 9999})
        assert result.ok
        assert result.output["exit_code"] == 0


# ---------------------------------------------------------------------------
# Blocklist
# ---------------------------------------------------------------------------

class TestBashBlocklist:
    @pytest.mark.parametrize("cmd", [
        "rm -rf /tmp",
        "sudo apt install vim",
        "dd if=/dev/zero of=/dev/sda",
        "mkfs.ext4 /dev/sdb",
        "shred /dev/sda",
        "reboot",
        "poweroff",
        "passwd root",
        "su root -c whoami",
    ])
    def test_blocked_commands(self, cmd: str):
        result = invoke_tool("bash", {"command": cmd})
        assert result.ok
        assert result.output["blocked"] is True
        assert result.output["exit_code"] == -1
        assert "blocked" in result.output["stderr"].lower() or "policy" in result.output["stderr"].lower()

    def test_safe_command_not_blocked(self):
        result = invoke_tool("bash", {"command": "ls /tmp"})
        assert result.ok
        assert result.output["blocked"] is False


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

class TestBashRedaction:
    def test_api_key_redacted(self):
        result = invoke_tool("bash", {"command": "echo 'api_key=supersecretvalue123'"})
        assert result.ok
        assert "supersecretvalue123" not in result.output["stdout"]
        assert "[REDACTED]" in result.output["stdout"]

    def test_token_redacted(self):
        result = invoke_tool("bash", {"command": "echo 'token=abcdefghijklmnop'"})
        assert result.ok
        assert "abcdefghijklmnop" not in result.output["stdout"]
        assert "[REDACTED]" in result.output["stdout"]

    def test_password_redacted(self):
        result = invoke_tool("bash", {"command": "echo 'password=mysecret'"})
        assert result.ok
        assert "mysecret" not in result.output["stdout"]
        assert "[REDACTED]" in result.output["stdout"]

    def test_safe_output_not_redacted(self):
        result = invoke_tool("bash", {"command": "echo 'no secrets here: 42'"})
        assert result.ok
        assert "no secrets here: 42" in result.output["stdout"]
