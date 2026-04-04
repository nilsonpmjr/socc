from __future__ import annotations

import io
import time
from contextlib import redirect_stdout


def _reset_harness_state() -> None:
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


def test_tui_entrypoint_bootstraps_harness_before_launch(monkeypatch):
    from socc.cli.main import main
    from socc.core.harness.runtime import RUNTIME

    _reset_harness_state()
    captured: dict[str, object] = {}

    def _fake_run_chat_tui(**kwargs):
        captured.update(kwargs)
        captured["bootstrapped"] = RUNTIME._initialised
        captured["commands"] = [item.name for item in RUNTIME.list_command_inventory(limit=20)]
        return 0

    monkeypatch.setattr("socc.cli.chat_interactive.run_chat_tui", _fake_run_chat_tui)

    exit_code = main(
        [
            "tui",
            "--session-id",
            "sess-123",
            "--cliente",
            "acme",
            "--backend",
            "ollama",
            "--model",
            "qwen-test",
        ]
    )

    assert exit_code == 0
    assert captured["bootstrapped"] is True
    assert "agents" in captured["commands"]
    assert captured["session_id"] == "sess-123"
    assert captured["cliente"] == "acme"
    assert captured["selected_backend"] == "ollama"
    assert captured["selected_model"] == "qwen-test"


def test_chat_interactive_entrypoint_bootstraps_harness_before_launch(monkeypatch):
    from socc.cli.main import main
    from socc.core.harness.runtime import RUNTIME

    _reset_harness_state()
    captured: dict[str, object] = {}

    def _fake_run_chat_tui(**kwargs):
        captured.update(kwargs)
        captured["bootstrapped"] = RUNTIME._initialised
        captured["tools"] = [item.name for item in RUNTIME.list_tool_inventory(limit=20)]
        return 0

    monkeypatch.setattr("socc.cli.chat_interactive.run_chat_tui", _fake_run_chat_tui)

    exit_code = main(
        [
            "chat",
            "--interactive",
            "--session-id",
            "chat-456",
            "--cliente",
            "globex",
            "--backend",
            "openai",
            "--model",
            "gpt-test",
        ]
    )

    assert exit_code == 0
    assert captured["bootstrapped"] is True
    assert "bash" in captured["tools"]
    assert captured["session_id"] == "chat-456"
    assert captured["cliente"] == "globex"
    assert captured["selected_backend"] == "openai"
    assert captured["selected_model"] == "gpt-test"


def test_startup_skips_unconfigured_plugins_without_breaking_runtime(monkeypatch):
    import socc.cli.startup as startup_mod
    from socc.core.harness.runtime import RUNTIME

    _reset_harness_state()

    def _fake_register_all_plugins(*, skip_unconfigured: bool = True):
        assert skip_unconfigured is True
        return {"virustotal": False, "misp": False}

    monkeypatch.setattr("socc.plugins.register_all_plugins", _fake_register_all_plugins)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        startup_mod.startup(block=True, verbose=True)

    rendered = stdout.getvalue().lower()
    assert "plugins skipped" in rendered
    assert RUNTIME._initialised is True
    assert any(item.name == "case" for item in RUNTIME.list_command_inventory(limit=20))


def test_startup_local_bootstrap_finishes_under_one_second():
    import socc.cli.startup as startup_mod
    from socc.core.harness.runtime import RUNTIME

    _reset_harness_state()

    started = time.perf_counter()
    startup_mod.startup(block=True)
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0
    assert RUNTIME._initialised is True
