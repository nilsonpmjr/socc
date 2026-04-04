from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest


@pytest.fixture
def temp_session_db(monkeypatch, tmp_path):
    from soc_copilot.modules import persistence as legacy_persistence

    db_path = tmp_path / "sessions.sqlite3"
    monkeypatch.setattr(legacy_persistence, "DB_PATH", str(db_path))
    return db_path


def _seed_session(session_id: str, *, cliente: str = "acme") -> None:
    from socc.core import storage

    storage.init_db()
    storage.ensure_chat_session(session_id, cliente=cliente, titulo="Investigação inicial")
    storage.save_chat_message(session_id, "user", "Primeira pergunta")
    storage.save_chat_message(session_id, "assistant", "Primeira resposta")


def test_session_resume_json_returns_summary(temp_session_db):
    from socc.cli.main import main

    _seed_session("sess-001")

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = main(["session", "resume", "sess-001", "--json"])

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["found"] is True
    assert payload["session"]["titulo"] == "Investigação inicial"
    assert payload["session"]["usage"]["messages"] == 2
    assert len(payload["messages"]) == 2


def test_session_resume_launches_tui_with_existing_session(monkeypatch, temp_session_db):
    from socc.cli.main import main

    _seed_session("sess-002", cliente="globex")
    captured: dict[str, object] = {}

    def _fake_run_chat_tui(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr("socc.cli.chat_interactive.run_chat_tui", _fake_run_chat_tui)

    exit_code = main(["session", "resume", "sess-002"])

    assert exit_code == 0
    assert captured["session_id"] == "sess-002"
    assert captured["cliente"] == "globex"


def test_session_show_prints_usage_summary(temp_session_db):
    from socc.cli.main import main

    _seed_session("sess-003")

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = main(["session", "show", "sess-003"])

    rendered = stdout.getvalue()
    assert exit_code == 0
    assert "usage:" in rendered
    assert "Primeira pergunta" in rendered


def test_session_list_includes_seeded_session(temp_session_db):
    from socc.cli.main import main

    _seed_session("sess-list")

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = main(["session", "list"])

    rendered = stdout.getvalue()
    assert exit_code == 0
    assert "sess-list" in rendered


def test_tui_resume_command_rehydrates_transcript(temp_session_db):
    from socc.cli.chat_interactive import SoccChatTUI

    _seed_session("sess-004")

    tui = SoccChatTUI(
        session_id="",
        cliente="",
        response_mode="balanced",
        selected_backend="",
        selected_model="",
        stream=False,
    )

    tui._handle_command("/resume sess-004")

    transcript = tui.history.get_plain()
    assert tui.session_id == "sess-004"
    assert "Primeira pergunta" in transcript
    assert "Primeira resposta" in transcript


def test_tui_constructor_preloads_existing_session(temp_session_db):
    from socc.cli.chat_interactive import SoccChatTUI

    _seed_session("sess-005")

    tui = SoccChatTUI(
        session_id="sess-005",
        cliente="",
        response_mode="balanced",
        selected_backend="",
        selected_model="",
        stream=False,
    )

    transcript = tui.history.get_plain()
    assert "Primeira pergunta" in transcript
    assert "Primeira resposta" in transcript


def test_engine_session_payload_returns_summary(temp_session_db):
    from socc.core.engine import get_chat_session_payload

    _seed_session("sess-payload", cliente="initech")

    payload = get_chat_session_payload("sess-payload", limit=10)

    assert payload["found"] is True
    assert payload["session"]["cliente"] == "initech"
    assert payload["session"]["usage"]["messages"] == 2
    assert len(payload["messages"]) == 2


def test_tui_help_differentiates_local_and_harness_commands(temp_session_db):
    from socc.cli.chat_interactive import SoccChatTUI

    tui = SoccChatTUI(
        session_id="",
        cliente="",
        response_mode="balanced",
        selected_backend="",
        selected_model="",
        stream=False,
    )

    tui._handle_command("/help case")

    transcript = tui.history.get_plain()
    assert "Comandos locais" in transcript
    assert "Comandos da harness" in transcript
    assert "/case" in transcript


def test_slash_surface_includes_local_and_harness_commands():
    import socc.cli.startup as startup_mod
    from socc.cli.chat_interactive import _slash_surface

    startup_mod._started = False
    startup_mod.startup(block=True)

    surface = _slash_surface()

    assert "/resume" in surface
    assert "/case" in surface
    assert "/agents" in surface


def test_tui_dispatches_unknown_slash_commands_via_runtime(monkeypatch):
    from socc.cli.chat_interactive import SoccChatTUI
    from socc.core.harness.models import CommandResult

    captured: dict[str, object] = {}

    def _fake_dispatch(raw_input: str, context=None):
        captured["raw_input"] = raw_input
        return CommandResult(ok=True, output="runtime dispatched")

    monkeypatch.setattr("socc.core.harness.runtime.RUNTIME.dispatch_command", _fake_dispatch)

    tui = SoccChatTUI(
        session_id="",
        cliente="",
        response_mode="balanced",
        selected_backend="",
        selected_model="",
        stream=False,
    )
    tui._handle_command("/case list")

    transcript = tui.history.get_plain()
    assert captured["raw_input"] == "/case list"
    assert "runtime dispatched" in transcript
