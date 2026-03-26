from __future__ import annotations

from dataclasses import dataclass
import os
import shutil

from soc_copilot.config import (
    ANTHROPIC_API_KEY,
    LLM_ENABLED,
    LLM_MODEL,
    LLM_PROVIDER,
    LLM_TIMEOUT,
    OLLAMA_MODEL,
    OLLAMA_URL,
)


@dataclass
class LLMRuntimeConfig:
    enabled: bool
    provider: str
    model: str
    timeout: float
    device: str
    endpoint: str


def gpu_available() -> bool:
    visible_devices = os.getenv("CUDA_VISIBLE_DEVICES", "").strip()
    if visible_devices and visible_devices != "-1":
        return True
    return shutil.which("nvidia-smi") is not None


def preferred_device() -> str:
    configured = os.getenv("SOCC_INFERENCE_DEVICE", "").strip().lower()
    if configured:
        return configured
    return "gpu" if gpu_available() else "cpu"


def resolve_runtime() -> LLMRuntimeConfig:
    provider = (LLM_PROVIDER or "ollama").lower()
    if provider == "anthropic":
        endpoint = "anthropic"
        model = LLM_MODEL
    else:
        endpoint = OLLAMA_URL
        model = OLLAMA_MODEL

    return LLMRuntimeConfig(
        enabled=LLM_ENABLED and bool(ANTHROPIC_API_KEY if provider == "anthropic" else endpoint),
        provider=provider,
        model=model,
        timeout=LLM_TIMEOUT,
        device=preferred_device(),
        endpoint=endpoint,
    )
