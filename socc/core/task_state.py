from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TaskState:
    """Minimal task lifecycle state kept separate from persisted session state."""

    task_id: str
    session_id: str
    kind: str
    status: str = "pending"
    source: str = ""
    phase: str = ""
    label: str = ""
    skill: str = ""
    input_preview: str = ""
    result_summary: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    subagent_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = time.time()

    def mark_completed(self, *, summary: str = "", error: str = "") -> None:
        self.status = "failed" if error else "completed"
        self.result_summary = summary or self.result_summary
        self.error = error or self.error
        self.completed_at = time.time()
        self.touch()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "kind": self.kind,
            "status": self.status,
            "source": self.source,
            "phase": self.phase,
            "label": self.label,
            "skill": self.skill,
            "input_preview": self.input_preview,
            "result_summary": self.result_summary,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "subagent_ids": list(self.subagent_ids),
            "metadata": dict(self.metadata),
        }


_TASKS: dict[str, TaskState] = {}
_LOCK = threading.Lock()


def create_task(
    *,
    session_id: str = "",
    kind: str,
    source: str = "",
    input_preview: str = "",
    skill: str = "",
    metadata: dict[str, Any] | None = None,
) -> TaskState:
    task = TaskState(
        task_id=uuid.uuid4().hex[:10],
        session_id=str(session_id or ""),
        kind=kind,
        source=source,
        input_preview=str(input_preview or "")[:160],
        skill=str(skill or ""),
        metadata=dict(metadata or {}),
    )
    with _LOCK:
        _TASKS[task.task_id] = task
    return task


def get_task(task_id: str) -> TaskState | None:
    with _LOCK:
        return _TASKS.get(task_id)


def list_tasks(*, limit: int = 50, status: str = "") -> list[TaskState]:
    with _LOCK:
        tasks = list(_TASKS.values())
    if status:
        tasks = [task for task in tasks if task.status == status]
    tasks.sort(key=lambda task: task.updated_at, reverse=True)
    return tasks[:limit]


def update_task(task_id: str, **changes: Any) -> TaskState | None:
    with _LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            return None
        for key, value in changes.items():
            if hasattr(task, key):
                setattr(task, key, value)
        task.touch()
        return task


def set_task_phase(task_id: str, *, phase: str, label: str = "") -> TaskState | None:
    with _LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            return None
        task.phase = phase
        task.label = label or task.label
        if task.status == "pending":
            task.status = "running"
        task.touch()
        return task


def complete_task(task_id: str, *, summary: str = "", error: str = "") -> TaskState | None:
    with _LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            return None
        task.mark_completed(summary=summary, error=error)
        return task


def attach_subagent(task_id: str, subagent_id: str) -> TaskState | None:
    with _LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            return None
        if subagent_id not in task.subagent_ids:
            task.subagent_ids.append(subagent_id)
        task.touch()
        return task


def clear_tasks() -> None:
    with _LOCK:
        _TASKS.clear()
