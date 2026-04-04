from __future__ import annotations

import asyncio


def _formatted_text_to_string(formatted) -> str:
    return "".join(fragment[1] for fragment in formatted)


def test_engine_stream_submission_preserves_tool_events(monkeypatch):
    from socc.core.engine import stream_chat_submission_events

    def _fake_stream_chat_reply_events(**kwargs):
        yield {"event": "meta", "session_id": "sess-tool", "skill": "soc-generalist", "runtime": {}, "model": "fake"}
        yield {"event": "tool_call", "tool": "bash", "arguments": {"command": "echo hi"}, "skill": "soc-generalist"}
        yield {"event": "tool_result", "content": "hi", "skill": "soc-generalist"}
        yield {"event": "delta", "delta": "ok", "skill": "soc-generalist"}
        yield {
            "event": "final",
            "data": {
                "type": "message",
                "content": "ok",
                "skill": "soc-generalist",
                "session_id": "sess-tool",
                "runtime": {},
                "tool_calls": [{"tool": "bash", "arguments": {"command": "echo hi"}}],
                "metadata": {"tool_results": [{"content": "hi"}]},
            },
        }

    monkeypatch.setattr(
        "socc.core.engine.chat_runtime.stream_chat_reply_events",
        _fake_stream_chat_reply_events,
    )

    async def _collect():
        return [
            event
            async for event in stream_chat_submission_events(
                message="hello",
                session_id="sess-tool",
            )
        ]

    events = asyncio.run(_collect())

    names = [event["event"] for event in events]
    assert "tool_call" in names
    assert "tool_result" in names
    final_payload = events[-1]["payload"]
    assert final_payload["tool_calls"][0]["tool"] == "bash"
    assert final_payload["metadata"]["tool_results"][0]["content"] == "hi"


def test_tui_renders_phase_and_tool_events(monkeypatch):
    from socc.cli.chat_interactive import SoccChatTUI

    async def _fake_stream_chat_submission_events(**kwargs):
        yield {"event": "meta", "payload": {"session_id": "sess-ui", "skill": "soc-generalist", "model": "fake"}}
        yield {"event": "phase", "payload": {"phase": "analysis", "label": "Classificando..."}}
        yield {"event": "tool_call", "payload": {"tool": "bash", "arguments": {"command": "echo hi"}}}
        yield {"event": "tool_result", "payload": {"content": "hi"}}
        yield {"event": "delta", "payload": {"delta": "Resposta final"}}
        yield {"event": "final", "payload": {"session_id": "sess-ui", "skill": "soc-generalist", "runtime": {}}}

    monkeypatch.setattr(
        "socc.core.engine.stream_chat_submission_events",
        _fake_stream_chat_submission_events,
    )

    tui = SoccChatTUI(
        session_id="sess-ui",
        cliente="",
        response_mode="balanced",
        selected_backend="ollama",
        selected_model="",
        stream=True,
    )

    tui._call_llm("hello")

    transcript = tui.history.get_plain()
    assert "Classificando..." in transcript
    assert "⚙ bash" in transcript
    assert "✓ hi" in transcript
    assert "Resposta final" in transcript
    assert "runtime  ◈ ollama/auto" in transcript
    assert "· analysis  Classificando..." in transcript
    assert "turn  " in transcript


def test_tui_chrome_sidebar_and_footer_are_more_informative(monkeypatch):
    from socc.cli.chat_interactive import SoccChatTUI

    monkeypatch.setattr(
        SoccChatTUI,
        "_get_session_summary",
        lambda self, session_id, limit=6: {
            "session_id": session_id,
            "titulo": "Sessão operacional",
            "cliente": "acme",
            "preview": "Último resumo do operador",
            "usage": {"messages": 4, "tokens_in": 120, "tokens_out": 80},
        },
    )

    tui = SoccChatTUI(
        session_id="sess-layout",
        cliente="acme",
        response_mode="balanced",
        selected_backend="ollama",
        selected_model="qwen",
        stream=False,
    )
    tui._last_skill = "triage"
    tui._last_phase = "analysis"
    tui._last_latency_ms = 42

    chrome = _formatted_text_to_string(tui._top_chrome_text())
    sidebar = _formatted_text_to_string(tui._sidebar_text())
    footer = _formatted_text_to_string(tui._footer_bar_text())

    assert "Sessão operacional" in chrome
    assert "idle/attached" in chrome
    assert "stats" in sidebar
    assert "4 msgs" in sidebar
    assert "Último resumo do operador" in sidebar
    assert "tab commands" in footer
    assert "attached" in footer
    assert "42ms" in footer


def test_tui_reflects_task_and_bridge_state(monkeypatch):
    from socc.cli.chat_interactive import SoccChatTUI
    from socc.core import session_bridge, task_state

    task_state.clear_tasks()
    session_bridge.clear_bridges()
    task = task_state.create_task(
        session_id="sess-ops",
        kind="remote_agent",
        source="test",
        input_preview="investigate",
        skill="triage",
    )
    task_state.update_task(task.task_id, status="running", phase="analysis", result_summary="awaiting remote response")
    bridge = session_bridge.create_session(
        session_id="sess-ops",
        mode="remote",
        remote_target="wss://bridge.example/ws",
    )
    session_bridge.set_transport_capability("http+ws", available=True, auth_mode="bearer")
    session_bridge.attach_session(bridge.bridge_id)

    monkeypatch.setattr(
        SoccChatTUI,
        "_get_session_summary",
        lambda self, session_id, limit=6: {
            "session_id": session_id,
            "titulo": "Sessão remota",
            "cliente": "globex",
            "preview": "bridge active",
            "usage": {"messages": 2, "tokens_in": 10, "tokens_out": 20},
        },
    )

    tui = SoccChatTUI(
        session_id="sess-ops",
        cliente="globex",
        response_mode="balanced",
        selected_backend="ollama",
        selected_model="qwen",
        stream=False,
    )
    tui._last_skill = "triage"
    tui._last_phase = "analysis"

    chrome = _formatted_text_to_string(tui._top_chrome_text())
    sidebar = _formatted_text_to_string(tui._sidebar_text())
    footer = _formatted_text_to_string(tui._footer_bar_text())
    status = _formatted_text_to_string(tui._status_bar_text())

    assert "running/attached" in chrome
    assert "remote · attached" in sidebar
    assert "bearer · http+ws" in sidebar
    assert "running · analysis" in sidebar
    assert "awaiting remote response" in sidebar
    assert "attached" in footer
    assert "idle/running" in footer
    assert "task running" in status


def test_degraded_remote_bridge_is_visible_in_layout(monkeypatch):
    from socc.cli.chat_interactive import SoccChatTUI
    from socc.core import session_bridge, task_state

    task_state.clear_tasks()
    session_bridge.clear_bridges()
    task = task_state.create_task(session_id="sess-degraded", kind="remote_agent", source="test")
    task_state.update_task(task.task_id, status="failed", phase="attach")
    bridge = session_bridge.create_session(
        session_id="sess-degraded",
        mode="remote",
        remote_target="wss://bridge.example/ws",
    )
    session_bridge.set_transport_capability("http+ws", available=False, auth_mode="bearer")
    session_bridge.attach_session(bridge.bridge_id)

    monkeypatch.setattr(
        SoccChatTUI,
        "_get_session_summary",
        lambda self, session_id, limit=6: {
            "session_id": session_id,
            "titulo": "Sessão degradada",
            "cliente": "initech",
            "preview": "",
            "usage": {"messages": 0, "tokens_in": 0, "tokens_out": 0},
        },
    )

    tui = SoccChatTUI(
        session_id="sess-degraded",
        cliente="initech",
        response_mode="balanced",
        selected_backend="ollama",
        selected_model="qwen",
        stream=False,
    )

    footer = _formatted_text_to_string(tui._footer_bar_text())
    sidebar = _formatted_text_to_string(tui._sidebar_text())

    assert "degraded" in footer
    assert "remote · degraded" in sidebar
    assert "failed · attach" in sidebar


def test_command_palette_surfaces_slash_command_context():
    import socc.cli.startup as startup_mod
    from socc.cli.chat_interactive import SoccChatTUI

    startup_mod._started = False
    startup_mod.startup(block=True)

    tui = SoccChatTUI(
        session_id="sess-cmd",
        cliente="",
        response_mode="balanced",
        selected_backend="ollama",
        selected_model="qwen",
        stream=False,
    )
    tui._on_input_value_change("/case create")

    palette = _formatted_text_to_string(tui._command_palette_text())

    assert "slash" in palette
    assert "/case" in palette
    assert "Manage incident cases" in palette
    assert "aliases" in palette


def test_command_palette_has_prompt_mode_when_not_in_slash_mode():
    from socc.cli.chat_interactive import SoccChatTUI

    tui = SoccChatTUI(
        session_id="sess-prompt",
        cliente="",
        response_mode="balanced",
        selected_backend="ollama",
        selected_model="qwen",
        stream=False,
    )
    tui._on_input_value_change("investigate this payload")

    palette = _formatted_text_to_string(tui._command_palette_text())

    assert "prompt" in palette
    assert "natural language / payload" in palette
    assert "enter send" in palette


def test_command_palette_hides_when_input_is_not_slash():
    from socc.cli.chat_interactive import SoccChatTUI

    tui = SoccChatTUI(
        session_id="sess-hide",
        cliente="",
        response_mode="balanced",
        selected_backend="ollama",
        selected_model="qwen",
        stream=False,
    )

    tui._on_input_value_change("hello world")
    assert tui._show_command_palette() is False

    tui._on_input_value_change("/case")
    assert tui._show_command_palette() is True


def test_prompt_badge_switches_between_msg_and_cmd():
    from socc.cli.chat_interactive import SoccChatTUI

    tui = SoccChatTUI(
        session_id="sess-badge",
        cliente="",
        response_mode="balanced",
        selected_backend="ollama",
        selected_model="qwen",
        stream=False,
    )

    tui._on_input_value_change("hello")
    assert tui._input_value == "hello"
    assert tui._show_command_palette() is False

    tui._on_input_value_change("/case")
    assert tui._input_value == "/case"
    assert tui._show_command_palette() is True


def test_transcript_mode_toggle_hides_sidebar():
    from socc.cli.chat_interactive import SoccChatTUI

    tui = SoccChatTUI(
        session_id="sess-transcript",
        cliente="",
        response_mode="balanced",
        selected_backend="ollama",
        selected_model="qwen",
        stream=False,
    )

    assert tui._transcript_mode is False
    tui._toggle_transcript_mode()
    assert tui._transcript_mode is True
    tui._toggle_transcript_mode()
    assert tui._transcript_mode is False


def test_submit_clears_command_palette_state():
    from socc.cli.chat_interactive import SoccChatTUI

    tui = SoccChatTUI(
        session_id="sess-clear",
        cliente="",
        response_mode="balanced",
        selected_backend="ollama",
        selected_model="qwen",
        stream=False,
    )

    tui._on_input_value_change("/case")
    assert tui._show_command_palette() is True

    class _Buffer:
        text = "/case"

        @staticmethod
        def reset():
            return None

    tui._on_submit(_Buffer())
    assert tui._input_value == ""
