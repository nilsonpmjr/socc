from __future__ import annotations

from pathlib import Path
from typing import Any

from soc_copilot.modules import soc_copilot_loader


LEGACY_MODULE = "soc_copilot.modules.soc_copilot_loader"


def load_agent_config(base_path: Path | None = None) -> Any:
    return soc_copilot_loader.load_soc_copilot(base_path=base_path)


def list_available_agents() -> list[dict[str, Any]]:
    return soc_copilot_loader.list_available_agents()


def choose_skill(
    user_input: str,
    *,
    artifact_type: str | None = None,
    available_skills: list[str] | None = None,
) -> str:
    return soc_copilot_loader.choose_skill(
        user_input=user_input,
        artifact_type=artifact_type,
        available_skills=available_skills,
    )


def build_prompt_context(
    *,
    user_input: str = "",
    artifact_type: str | None = None,
    session_context: str = "",
    selected_skill: str | None = None,
) -> dict[str, str]:
    return soc_copilot_loader.build_prompt_context(
        user_input=user_input,
        artifact_type=artifact_type,
        session_context=session_context,
        selected_skill=selected_skill,
    )
