from __future__ import annotations


def test_local_session_bridge_create_attach_close():
    from socc.core import session_bridge

    session_bridge.clear_bridges()
    handle = session_bridge.create_session(session_id="sess-local", mode="local")

    assert handle.state == "created"
    attached = session_bridge.attach_session(handle.bridge_id)
    assert attached is not None
    assert attached.state == "attached"
    assert attached.transport_state == "attached"

    closed = session_bridge.close_session(handle.bridge_id)
    assert closed is not None
    assert closed.state == "closed"
    assert closed.transport_state == "disconnected"


def test_remote_session_bridge_degrades_when_transport_unavailable():
    from socc.core import session_bridge

    session_bridge.clear_bridges()
    session_bridge.set_transport_capability("http+ws", available=False, auth_mode="bearer")

    handle = session_bridge.create_session(
        session_id="sess-remote",
        mode="remote",
        remote_target="wss://bridge.example/ws",
    )
    attached = session_bridge.attach_session(handle.bridge_id)

    assert attached is not None
    assert attached.state == "error"
    assert attached.transport_state == "degraded"
    assert "transport_unavailable:http+ws" == attached.error


def test_remote_session_bridge_resume_after_pause_when_transport_available():
    from socc.core import session_bridge

    session_bridge.clear_bridges()
    session_bridge.set_transport_capability("http+ws", available=True, auth_mode="bearer")

    handle = session_bridge.create_session(session_id="sess-remote-ok", mode="remote")
    attached = session_bridge.attach_session(handle.bridge_id)
    assert attached is not None
    assert attached.state == "attached"

    paused = session_bridge.pause_session(handle.bridge_id)
    assert paused is not None
    assert paused.state == "paused"

    resumed = session_bridge.resume_session(handle.bridge_id)
    assert resumed is not None
    assert resumed.state == "attached"
    assert resumed.transport_state == "attached"
