from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field


SESSION_STATES = {
    "created",
    "connecting",
    "attached",
    "paused",
    "closed",
    "error",
}

TRANSPORT_STATES = {
    "disconnected",
    "connecting",
    "attached",
    "degraded",
}


@dataclass(slots=True)
class SessionBridgeHandle:
    bridge_id: str
    session_id: str
    mode: str = "local"  # local | remote
    state: str = "created"
    transport: str = "memory"
    transport_state: str = "disconnected"
    auth_mode: str = "none"
    remote_target: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    error: str = ""

    def touch(self) -> None:
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, object]:
        return {
            "bridge_id": self.bridge_id,
            "session_id": self.session_id,
            "mode": self.mode,
            "state": self.state,
            "transport": self.transport,
            "transport_state": self.transport_state,
            "auth_mode": self.auth_mode,
            "remote_target": self.remote_target,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }


_BRIDGES: dict[str, SessionBridgeHandle] = {}
_LOCK = threading.Lock()
_TRANSPORT_CAPS: dict[str, dict[str, object]] = {
    "memory": {"available": True, "auth_mode": "none"},
    "http+ws": {"available": False, "auth_mode": "bearer"},
}


def set_transport_capability(
    transport: str,
    *,
    available: bool,
    auth_mode: str = "",
) -> None:
    with _LOCK:
        current = dict(_TRANSPORT_CAPS.get(transport, {}))
        current["available"] = bool(available)
        if auth_mode:
            current["auth_mode"] = auth_mode
        _TRANSPORT_CAPS[transport] = current


def get_transport_capability(transport: str) -> dict[str, object]:
    with _LOCK:
        return dict(_TRANSPORT_CAPS.get(transport, {}))


def create_session(
    *,
    session_id: str = "",
    mode: str = "local",
    transport: str = "",
    remote_target: str = "",
) -> SessionBridgeHandle:
    normalized_mode = "remote" if str(mode).strip().lower() == "remote" else "local"
    chosen_transport = transport or ("http+ws" if normalized_mode == "remote" else "memory")
    caps = get_transport_capability(chosen_transport)
    handle = SessionBridgeHandle(
        bridge_id=uuid.uuid4().hex[:10],
        session_id=str(session_id or uuid.uuid4().hex[:12]),
        mode=normalized_mode,
        state="created",
        transport=chosen_transport,
        transport_state="disconnected",
        auth_mode=str(caps.get("auth_mode") or "none"),
        remote_target=str(remote_target or ""),
    )
    with _LOCK:
        _BRIDGES[handle.bridge_id] = handle
    return handle


def get_bridge(bridge_id: str) -> SessionBridgeHandle | None:
    with _LOCK:
        return _BRIDGES.get(bridge_id)


def list_bridges(limit: int = 50) -> list[SessionBridgeHandle]:
    with _LOCK:
        handles = list(_BRIDGES.values())
    handles.sort(key=lambda item: item.updated_at, reverse=True)
    return handles[:limit]


def attach_session(bridge_id: str) -> SessionBridgeHandle | None:
    with _LOCK:
        handle = _BRIDGES.get(bridge_id)
        if handle is None:
            return None
        if handle.mode == "local":
            handle.state = "attached"
            handle.transport_state = "attached"
            handle.error = ""
            handle.touch()
            return handle

        caps = _TRANSPORT_CAPS.get(handle.transport, {})
        handle.state = "connecting"
        handle.transport_state = "connecting"
        handle.touch()
        if not bool(caps.get("available")):
            handle.state = "error"
            handle.transport_state = "degraded"
            handle.error = f"transport_unavailable:{handle.transport}"
            handle.touch()
            return handle

        handle.state = "attached"
        handle.transport_state = "attached"
        handle.error = ""
        handle.touch()
        return handle


def resume_session(bridge_id: str) -> SessionBridgeHandle | None:
    with _LOCK:
        handle = _BRIDGES.get(bridge_id)
        if handle is None:
            return None
        if handle.state == "paused":
            handle.state = "created"
            handle.transport_state = "disconnected"
            handle.touch()
    return attach_session(bridge_id)


def pause_session(bridge_id: str) -> SessionBridgeHandle | None:
    with _LOCK:
        handle = _BRIDGES.get(bridge_id)
        if handle is None:
            return None
        handle.state = "paused"
        handle.transport_state = "disconnected"
        handle.touch()
        return handle


def close_session(bridge_id: str) -> SessionBridgeHandle | None:
    with _LOCK:
        handle = _BRIDGES.get(bridge_id)
        if handle is None:
            return None
        handle.state = "closed"
        handle.transport_state = "disconnected"
        handle.touch()
        return handle


def clear_bridges() -> None:
    with _LOCK:
        _BRIDGES.clear()
