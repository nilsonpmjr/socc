from __future__ import annotations

import asyncio


def test_chat_reply_creates_task_state(monkeypatch):
    from socc.core import task_state as task_state_runtime
    from socc.core.engine import chat_reply

    task_state_runtime.clear_tasks()

    monkeypatch.setattr(
        "socc.core.engine.chat_runtime.generate_chat_reply",
        lambda **kwargs: {
            "type": "message",
            "content": "ok",
            "skill": "soc-generalist",
            "session_id": "sess-task",
            "runtime": {},
        },
    )

    payload = chat_reply("hello", session_id="sess-task")

    assert payload["task"]["session_id"] == "sess-task"
    assert payload["task"]["kind"] == "chat_reply"
    assert payload["task"]["status"] == "completed"
    assert payload["task"]["result_summary"] == "ok"


def test_stream_chat_submission_meta_exposes_task(monkeypatch):
    from socc.core import task_state as task_state_runtime
    from socc.core.engine import stream_chat_submission_events

    task_state_runtime.clear_tasks()

    def _fake_stream_chat_events(**kwargs):
        yield {"event": "meta", "session_id": "sess-stream", "skill": "soc-generalist", "runtime": {}, "model": "fake"}
        yield {
            "event": "final",
            "data": {
                "type": "message",
                "content": "done",
                "skill": "soc-generalist",
                "session_id": "sess-stream",
                "runtime": {},
            },
        }

    monkeypatch.setattr("socc.core.engine.stream_chat_events", _fake_stream_chat_events)

    async def _collect():
        return [event async for event in stream_chat_submission_events(message="hello", session_id="sess-stream")]

    events = asyncio.run(_collect())

    assert events[0]["payload"]["task"]["status"] in {"running", "pending"}
    assert events[-1]["payload"]["task"]["status"] == "completed"
    assert events[-1]["payload"]["task"]["session_id"] == "sess-stream"


def test_subagent_can_attach_to_existing_task(monkeypatch):
    from socc.agents.fork import SubagentConfig, fork_subagent
    from socc.core import task_state as task_state_runtime

    task_state_runtime.clear_tasks()
    task = task_state_runtime.create_task(session_id="sess-sub", kind="chat_reply", source="test")

    monkeypatch.setattr(
        "socc.core.chat.generate_chat_reply",
        lambda **kwargs: {"type": "message", "content": "- finding", "session_id": "sess-sub"},
    )

    handle = fork_subagent(
        SubagentConfig(
            name="sub-task",
            specialty="soc_analyst",
            task="inspect",
            task_id=task.task_id,
            timeout_seconds=30,
        ),
        block=True,
    )

    linked = task_state_runtime.get_task(task.task_id)
    assert linked is not None
    assert handle.id in linked.subagent_ids
