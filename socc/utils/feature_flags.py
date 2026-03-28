from __future__ import annotations

import os
from dataclasses import asdict, dataclass


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class FeatureFlags:
    analyze_api: bool
    draft_api: bool
    chat_api: bool
    chat_streaming: bool
    feedback_api: bool
    export_api: bool
    threat_intel: bool
    runtime_api: bool


FEATURE_FLAG_ENVS = {
    "analyze_api": "SOCC_FEATURE_ANALYZE_API",
    "draft_api": "SOCC_FEATURE_DRAFT_API",
    "chat_api": "SOCC_FEATURE_CHAT_API",
    "chat_streaming": "SOCC_FEATURE_CHAT_STREAMING",
    "feedback_api": "SOCC_FEATURE_FEEDBACK_API",
    "export_api": "SOCC_FEATURE_EXPORT_API",
    "threat_intel": "SOCC_FEATURE_THREAT_INTEL",
    "runtime_api": "SOCC_FEATURE_RUNTIME_API",
}


def resolve_feature_flags() -> FeatureFlags:
    return FeatureFlags(
        analyze_api=_env_flag(FEATURE_FLAG_ENVS["analyze_api"], True),
        draft_api=_env_flag(FEATURE_FLAG_ENVS["draft_api"], True),
        chat_api=_env_flag(FEATURE_FLAG_ENVS["chat_api"], True),
        chat_streaming=_env_flag(FEATURE_FLAG_ENVS["chat_streaming"], True),
        feedback_api=_env_flag(FEATURE_FLAG_ENVS["feedback_api"], True),
        export_api=_env_flag(FEATURE_FLAG_ENVS["export_api"], True),
        threat_intel=_env_flag(FEATURE_FLAG_ENVS["threat_intel"], True),
        runtime_api=_env_flag(FEATURE_FLAG_ENVS["runtime_api"], True),
    )


def feature_flags_payload() -> dict[str, bool]:
    return asdict(resolve_feature_flags())
