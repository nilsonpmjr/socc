from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import os
import queue
import shutil
import subprocess
import threading
import time
from urllib.parse import urlparse
from statistics import fmean
from typing import Any

try:
    import resource
except ImportError:  # pragma: no cover - Windows fallback
    resource = None

from soc_copilot.config import (
    ANTHROPIC_API_KEY,
    LLM_ENABLED,
    LLM_MODEL,
    LLM_PROVIDER,
    LLM_TIMEOUT,
    OLLAMA_MODEL,
    OLLAMA_URL,
)
from socc.core.memory import write_runtime_log
from socc.utils.safety import (
    log_redaction_enabled,
    prompt_audit_enabled,
    prompt_preview,
    prompt_preview_chars,
    redact_sensitive_text,
)


@dataclass
class LLMRuntimeConfig:
    enabled: bool
    backend: str
    backend_label: str
    backend_family: str
    backend_source: str
    backend_local: bool
    backend_gpu_supported: bool
    backend_streaming_supported: bool
    backend_embeddings_supported: bool
    provider: str
    model: str
    timeout: float
    device: str
    endpoint: str
    gpu_available: bool
    fallback_enabled: bool
    fallback_provider: str
    max_concurrency: int
    cpu_guard_enabled: bool
    cpu_guard_load: float


_EVENTS: deque[dict[str, Any]] = deque(maxlen=100)
_ANALYSIS_EVENTS: deque[dict[str, Any]] = deque(maxlen=200)


@dataclass(frozen=True)
class InferenceBackendSpec:
    key: str
    label: str
    provider: str
    family: str
    local: bool
    gpu_supported: bool
    streaming_supported: bool
    embeddings_supported: bool
    endpoint_env: str
    model_env: str
    endpoint_default: str
    model_default: str
    probe_strategy: str
    notes: str


def supported_backend_specs() -> dict[str, InferenceBackendSpec]:
    return {
        "ollama": InferenceBackendSpec(
            key="ollama",
            label="Ollama Local",
            provider="ollama",
            family="local-http",
            local=True,
            gpu_supported=True,
            streaming_supported=True,
            embeddings_supported=True,
            endpoint_env="OLLAMA_URL",
            model_env="OLLAMA_MODEL",
            endpoint_default=OLLAMA_URL,
            model_default=OLLAMA_MODEL,
            probe_strategy="ollama-tags",
            notes="Bom padrão local para workstation; suporta streaming incremental e costuma aproveitar GPU quando disponível.",
        ),
        "lmstudio": InferenceBackendSpec(
            key="lmstudio",
            label="LM Studio",
            provider="openai-compatible",
            family="openai-compatible",
            local=True,
            gpu_supported=True,
            streaming_supported=True,
            embeddings_supported=True,
            endpoint_env="SOCC_LMSTUDIO_URL",
            model_env="SOCC_LMSTUDIO_MODEL",
            endpoint_default="http://127.0.0.1:1234/v1",
            model_default="",
            probe_strategy="openai-models",
            notes="Boa opção desktop com API OpenAI-compatible local; útil para testes rápidos e comparação de modelos.",
        ),
        "vllm": InferenceBackendSpec(
            key="vllm",
            label="vLLM",
            provider="openai-compatible",
            family="openai-compatible",
            local=True,
            gpu_supported=True,
            streaming_supported=True,
            embeddings_supported=True,
            endpoint_env="SOCC_VLLM_URL",
            model_env="SOCC_VLLM_MODEL",
            endpoint_default="http://127.0.0.1:8000/v1",
            model_default="",
            probe_strategy="openai-models",
            notes="Backend indicado para inferência local com foco em throughput e uso de GPU em servidor dedicado.",
        ),
        "openai-compatible": InferenceBackendSpec(
            key="openai-compatible",
            label="OpenAI-Compatible",
            provider="openai-compatible",
            family="openai-compatible",
            local=False,
            gpu_supported=False,
            streaming_supported=True,
            embeddings_supported=True,
            endpoint_env="SOCC_OPENAI_COMPAT_URL",
            model_env="SOCC_OPENAI_COMPAT_MODEL",
            endpoint_default="",
            model_default="",
            probe_strategy="openai-models",
            notes="Permite plugar gateways compatíveis com OpenAI, locais ou remotos, mantendo um contrato único.",
        ),
        "anthropic": InferenceBackendSpec(
            key="anthropic",
            label="Anthropic",
            provider="anthropic",
            family="remote-api",
            local=False,
            gpu_supported=False,
            streaming_supported=True,
            embeddings_supported=False,
            endpoint_env="ANTHROPIC_API_KEY",
            model_env="LLM_MODEL",
            endpoint_default="anthropic",
            model_default=LLM_MODEL,
            probe_strategy="anthropic-key",
            notes="Fallback remoto útil quando não há backend local operacional ou quando a qualidade supera a latência.",
        ),
    }


def gpu_available() -> bool:
    visible_devices = os.getenv("CUDA_VISIBLE_DEVICES", "").strip()
    if visible_devices and visible_devices != "-1":
        return True
    return shutil.which("nvidia-smi") is not None


def _normalize_backend_key(value: str) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "auto": "auto",
        "ollama": "ollama",
        "anthropic": "anthropic",
        "lm-studio": "lmstudio",
        "lmstudio": "lmstudio",
        "vllm": "vllm",
        "openai": "openai-compatible",
        "openai_compatible": "openai-compatible",
        "openai-compatible": "openai-compatible",
    }
    return aliases.get(normalized, normalized)


def configured_backend() -> str:
    configured = _normalize_backend_key(os.getenv("SOCC_INFERENCE_BACKEND", ""))
    if configured in {"auto", *supported_backend_specs().keys()}:
        return configured or "auto"
    return "auto"


def backend_priority() -> list[str]:
    raw = os.getenv("SOCC_BACKEND_PRIORITY", "").strip()
    if not raw:
        return ["ollama", "lmstudio", "vllm", "openai-compatible", "anthropic"]
    items: list[str] = []
    for chunk in raw.split(","):
        key = _normalize_backend_key(chunk)
        if key in supported_backend_specs() and key not in items:
            items.append(key)
    return items or ["ollama", "lmstudio", "vllm", "openai-compatible", "anthropic"]


def fallback_provider() -> str:
    configured = os.getenv("SOCC_LLM_FALLBACK_PROVIDER", "").strip().lower()
    if configured in {"anthropic", "ollama", "lmstudio", "vllm", "openai-compatible", "cpu", "deterministic"}:
        return configured
    return "anthropic"


def preferred_device() -> str:
    configured = os.getenv("SOCC_INFERENCE_DEVICE", "").strip().lower()
    if configured:
        return configured
    return "gpu" if gpu_available() else "cpu"


def cpu_guard_enabled() -> bool:
    return os.getenv("SOCC_CPU_GUARD_ENABLED", "true").strip().lower() in {"1", "true", "yes"}


def cpu_guard_load() -> float:
    try:
        return float(os.getenv("SOCC_CPU_GUARD_LOAD", "4.0"))
    except ValueError:
        return 4.0


def max_concurrency() -> int:
    try:
        return max(1, int(os.getenv("SOCC_MAX_CONCURRENT_LLM", "2")))
    except ValueError:
        return 2


_INFERENCE_SEMAPHORE = threading.BoundedSemaphore(value=max_concurrency())


def _backend_endpoint(spec: InferenceBackendSpec) -> str:
    return os.getenv(spec.endpoint_env, spec.endpoint_default).strip() or spec.endpoint_default


def _backend_model(spec: InferenceBackendSpec) -> str:
    value = os.getenv(spec.model_env, spec.model_default).strip()
    if value:
        return value
    if spec.key == "anthropic":
        return LLM_MODEL
    if spec.key == "ollama":
        return OLLAMA_MODEL
    return os.getenv("SOCC_LOCAL_MODEL_DEFAULT", "").strip() or OLLAMA_MODEL


def _endpoint_looks_local(endpoint: str) -> bool:
    if not endpoint or endpoint == "anthropic":
        return False
    parsed = urlparse(endpoint)
    hostname = (parsed.hostname or "").strip().lower()
    return hostname in {"127.0.0.1", "localhost", "::1"}


def describe_backend_choice() -> dict[str, Any]:
    specs = supported_backend_specs()
    configured = configured_backend()
    source = "SOCC_INFERENCE_BACKEND" if configured != "auto" else "legacy-provider"
    if configured == "auto":
        inferred = "anthropic" if (LLM_PROVIDER or "ollama").lower() == "anthropic" else "ollama"
        selected = inferred if inferred in specs else backend_priority()[0]
    else:
        selected = configured

    spec = specs.get(selected, specs["ollama"])
    endpoint = _backend_endpoint(spec)
    model = _backend_model(spec)
    local_endpoint = _endpoint_looks_local(endpoint)
    backend_local = spec.local or local_endpoint
    return {
        "selected": spec.key,
        "source": source,
        "spec": spec,
        "endpoint": endpoint,
        "model": model,
        "backend_local": backend_local,
        "priority": backend_priority(),
    }


def supported_backends_payload() -> list[dict[str, Any]]:
    selected = describe_backend_choice().get("selected")
    payload: list[dict[str, Any]] = []
    for spec in supported_backend_specs().values():
        endpoint = _backend_endpoint(spec)
        model = _backend_model(spec)
        local_endpoint = _endpoint_looks_local(endpoint)
        payload.append(
            {
                "key": spec.key,
                "label": spec.label,
                "provider": spec.provider,
                "family": spec.family,
                "selected": spec.key == selected,
                "local": spec.local or local_endpoint,
                "gpu_supported": spec.gpu_supported,
                "streaming_supported": spec.streaming_supported,
                "embeddings_supported": spec.embeddings_supported,
                "endpoint": endpoint,
                "model": model,
                "endpoint_env": spec.endpoint_env,
                "model_env": spec.model_env,
                "probe_strategy": spec.probe_strategy,
                "notes": spec.notes,
            }
        )
    return payload


def resolve_runtime() -> LLMRuntimeConfig:
    backend_choice = describe_backend_choice()
    spec = backend_choice["spec"]
    provider = spec.provider
    gpu = gpu_available()
    endpoint = str(backend_choice["endpoint"])
    model = str(backend_choice["model"])
    backend_local = bool(backend_choice["backend_local"])
    preferred = preferred_device()
    effective_device = preferred if backend_local else "remote"
    runtime_enabled = False
    if provider == "anthropic":
        runtime_enabled = LLM_ENABLED and bool(ANTHROPIC_API_KEY)
    elif provider == "openai-compatible":
        runtime_enabled = LLM_ENABLED and bool(endpoint)
    else:
        runtime_enabled = LLM_ENABLED and bool(endpoint)

    return LLMRuntimeConfig(
        enabled=runtime_enabled,
        backend=spec.key,
        backend_label=spec.label,
        backend_family=spec.family,
        backend_source=str(backend_choice["source"]),
        backend_local=backend_local,
        backend_gpu_supported=spec.gpu_supported,
        backend_streaming_supported=spec.streaming_supported,
        backend_embeddings_supported=spec.embeddings_supported,
        provider=provider,
        model=model,
        timeout=LLM_TIMEOUT,
        device=effective_device,
        endpoint=endpoint,
        gpu_available=gpu,
        fallback_enabled=True,
        fallback_provider=fallback_provider(),
        max_concurrency=max_concurrency(),
        cpu_guard_enabled=cpu_guard_enabled(),
        cpu_guard_load=cpu_guard_load(),
    )


def _cpu_snapshot() -> dict[str, Any]:
    load_avg = None
    try:
        load_avg = os.getloadavg()
    except (AttributeError, OSError):
        load_avg = None

    usage = None
    if resource is not None:
        try:
            usage_raw = resource.getrusage(resource.RUSAGE_SELF)
            usage = {
                "user_time_sec": round(float(usage_raw.ru_utime), 4),
                "system_time_sec": round(float(usage_raw.ru_stime), 4),
                "max_rss_kb": int(getattr(usage_raw, "ru_maxrss", 0)),
            }
        except Exception:
            usage = None

    return {
        "load_avg": [round(value, 3) for value in load_avg] if load_avg else [],
        "process": usage or {},
    }


def cpu_guard_reason(runtime: LLMRuntimeConfig | None = None) -> str:
    current = runtime or resolve_runtime()
    if current.device != "cpu" or not current.cpu_guard_enabled:
        return ""
    cpu = _cpu_snapshot()
    loads = cpu.get("load_avg") or []
    if loads and isinstance(loads[0], (int, float)) and float(loads[0]) > current.cpu_guard_load:
        return f"cpu_guard_load_exceeded:{loads[0]}"
    return ""


def _gpu_snapshot() -> dict[str, Any]:
    if not gpu_available():
        return {"available": False, "devices": []}

    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return {"available": True, "devices": []}

    try:
        result = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=name,memory.total,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return {"available": True, "devices": []}

    devices = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 4:
            continue
        name, memory_total, memory_used, utilization = parts
        devices.append(
            {
                "name": name,
                "memory_total_mb": int(memory_total) if memory_total.isdigit() else memory_total,
                "memory_used_mb": int(memory_used) if memory_used.isdigit() else memory_used,
                "utilization_gpu_pct": int(utilization) if utilization.isdigit() else utilization,
            }
        )
    return {"available": True, "devices": devices}


def record_inference_event(
    *,
    source: str,
    provider: str,
    model: str,
    requested_device: str,
    effective_device: str,
    latency_ms: float,
    success: bool,
    fallback_used: bool = False,
    error: str = "",
) -> dict[str, Any]:
    event = {
        "timestamp": int(time.time()),
        "source": source,
        "provider": provider,
        "model": model,
        "requested_device": requested_device,
        "effective_device": effective_device,
        "latency_ms": round(float(latency_ms), 2),
        "success": bool(success),
        "fallback_used": bool(fallback_used),
        "error": redact_sensitive_text(str(error).strip(), limit=240),
    }
    _EVENTS.append(event)
    try:
        write_runtime_log(
            (
                f"{event['timestamp']} provider={provider} model={model} source={source} "
                f"device={effective_device} latency_ms={event['latency_ms']} "
                f"success={event['success']} fallback={event['fallback_used']} error={event['error']}"
            ),
            filename="runtime-metrics.log",
        )
    except OSError:
        pass
    return event


def record_prompt_audit(
    *,
    source: str,
    provider: str,
    model: str,
    prompt_text: str,
    skill: str = "",
) -> dict[str, Any]:
    summary = prompt_preview(prompt_text)
    event = {
        "timestamp": int(time.time()),
        "source": source,
        "provider": provider,
        "model": model,
        "skill": skill,
        "fingerprint": summary["fingerprint"],
        "chars": summary["chars"],
        "preview": summary["preview"],
    }
    if prompt_audit_enabled():
        try:
            write_runtime_log(
                (
                    f"{event['timestamp']} source={source} provider={provider} model={model} "
                    f"skill={skill or '-'} prompt_hash={event['fingerprint']} "
                    f"prompt_chars={event['chars']} prompt_preview={event['preview']}"
                ),
                filename="prompt-audit.log",
            )
        except OSError:
            pass
    return event


def record_analysis_event(
    *,
    source: str,
    latency_ms: float,
    schema_valid: bool,
    success: bool = True,
    threat_intel_used: bool = False,
    payload_hash: str = "",
    error: str = "",
) -> dict[str, Any]:
    event = {
        "timestamp": int(time.time()),
        "source": source,
        "latency_ms": round(float(latency_ms), 2),
        "schema_valid": bool(schema_valid),
        "success": bool(success),
        "threat_intel_used": bool(threat_intel_used),
        "payload_hash": str(payload_hash or "").strip(),
        "error": redact_sensitive_text(str(error).strip(), limit=240),
    }
    _ANALYSIS_EVENTS.append(event)
    try:
        write_runtime_log(
            (
                f"{event['timestamp']} source={source} latency_ms={event['latency_ms']} "
                f"success={event['success']} schema_valid={event['schema_valid']} "
                f"threat_intel={event['threat_intel_used']} payload_hash={event['payload_hash'] or '-'} "
                f"error={event['error'] or '-'}"
            ),
            filename="analysis-metrics.log",
        )
    except OSError:
        pass
    return event


@contextmanager
def inference_guard(runtime: LLMRuntimeConfig | None = None):
    current = runtime or resolve_runtime()
    reason = cpu_guard_reason(current)
    if reason:
        yield False, reason
        return

    acquired = _INFERENCE_SEMAPHORE.acquire(blocking=False)
    if not acquired:
        yield False, "max_concurrency_reached"
        return

    try:
        yield True, ""
    finally:
        try:
            _INFERENCE_SEMAPHORE.release()
        except ValueError:
            pass


def recent_events(limit: int = 20) -> list[dict[str, Any]]:
    items = list(_EVENTS)
    return items[-max(1, min(limit, len(items) or 1)) :] if items else []


def metrics_summary() -> dict[str, Any]:
    events = list(_EVENTS)
    analysis_events = list(_ANALYSIS_EVENTS)
    latencies = [event["latency_ms"] for event in events if isinstance(event.get("latency_ms"), (int, float))]
    analysis_latencies = [
        event["latency_ms"]
        for event in analysis_events
        if isinstance(event.get("latency_ms"), (int, float))
    ]
    errors = [event for event in events if not event.get("success")]
    fallbacks = [event for event in events if event.get("fallback_used")]
    providers = sorted({event.get("provider", "") for event in events if event.get("provider")})
    analysis_errors = [event for event in analysis_events if not event.get("success")]
    schema_valid = [event for event in analysis_events if event.get("schema_valid")]
    schema_invalid = [event for event in analysis_events if not event.get("schema_valid")]
    return {
        "total_events": len(events),
        "success_count": len(events) - len(errors),
        "error_count": len(errors),
        "fallback_count": len(fallbacks),
        "avg_latency_ms": round(fmean(latencies), 2) if latencies else 0.0,
        "providers_seen": providers,
        "last_event": events[-1] if events else {},
        "analysis_pipeline": {
            "total_events": len(analysis_events),
            "error_count": len(analysis_errors),
            "schema_valid_count": len(schema_valid),
            "schema_invalid_count": len(schema_invalid),
            "schema_valid_rate": round(len(schema_valid) / len(analysis_events), 4) if analysis_events else 0.0,
            "avg_latency_ms": round(fmean(analysis_latencies), 2) if analysis_latencies else 0.0,
            "last_event": analysis_events[-1] if analysis_events else {},
        },
    }


def runtime_brief() -> dict[str, Any]:
    config = resolve_runtime()
    return {
        "enabled": config.enabled,
        "backend": config.backend,
        "backend_label": config.backend_label,
        "backend_family": config.backend_family,
        "provider": config.provider,
        "model": config.model,
        "device": config.device,
        "gpu_available": config.gpu_available,
        "fallback_provider": config.fallback_provider,
    }


def runtime_status() -> dict[str, Any]:
    config = resolve_runtime()
    cpu = _cpu_snapshot()
    gpu = _gpu_snapshot()
    return {
        "runtime": asdict(config),
        "backends": {
            "selected": config.backend,
            "priority": backend_priority(),
            "supported": supported_backends_payload(),
        },
        "resources": {
            "cpu": cpu,
            "gpu": gpu,
        },
        "metrics": metrics_summary(),
        "safety": {
            "log_redaction_enabled": log_redaction_enabled(),
            "prompt_audit_enabled": prompt_audit_enabled(),
            "prompt_preview_chars": prompt_preview_chars(),
        },
    }


def probe_inference_backend(timeout: float = 2.0) -> dict[str, Any]:
    runtime = resolve_runtime()
    result = {
        "backend": runtime.backend,
        "provider": runtime.provider,
        "endpoint": runtime.endpoint,
        "reachable": False,
        "latency_ms": 0.0,
        "details": {},
        "error": "",
    }

    if runtime.backend == "anthropic":
        result["reachable"] = bool(ANTHROPIC_API_KEY)
        result["details"] = {"api_key_configured": bool(ANTHROPIC_API_KEY)}
        if not result["reachable"]:
            result["error"] = "anthropic_api_key_missing"
        return result

    import requests

    endpoint = str(runtime.endpoint).rstrip("/")
    if not endpoint:
        result["error"] = "backend_endpoint_missing"
        return result
    models_url = f"{endpoint}/models"
    if runtime.backend == "ollama":
        models_url = f"{endpoint}/api/tags"
    started = time.perf_counter()
    try:
        response = requests.get(models_url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        models = payload.get("models", []) if isinstance(payload, dict) else []
        if runtime.backend == "ollama" and isinstance(models, list):
            model_names = [item.get("name", "") for item in models[:10] if isinstance(item, dict)]
        else:
            model_names = [
                item.get("id", "") or item.get("name", "")
                for item in models[:10]
                if isinstance(item, dict)
            ]
        result["reachable"] = True
        result["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        result["details"] = {
            "backend_family": runtime.backend_family,
            "models_available": len(models),
            "model_names": model_names,
        }
        return result
    except Exception as exc:
        result["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        result["error"] = str(exc)
        return result


def list_backend_models(timeout: float = 2.0) -> dict[str, Any]:
    runtime = resolve_runtime()
    payload: dict[str, Any] = {
        "backend": runtime.backend,
        "provider": runtime.provider,
        "endpoint": runtime.endpoint,
        "reachable": False,
        "models": [],
        "error": "",
    }

    if runtime.backend == "anthropic":
        payload["error"] = "model_listing_not_supported"
        return payload

    import requests

    endpoint = str(runtime.endpoint).rstrip("/")
    if not endpoint:
        payload["error"] = "backend_endpoint_missing"
        return payload

    models_url = f"{endpoint}/models"
    parser = "openai-compatible"
    if runtime.backend == "ollama":
        models_url = f"{endpoint}/api/tags"
        parser = "ollama"

    try:
        response = requests.get(models_url, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        raw_models = data.get("models", []) if isinstance(data, dict) else []
        models: list[dict[str, Any]] = []
        if parser == "ollama":
            for item in raw_models:
                if not isinstance(item, dict):
                    continue
                models.append(
                    {
                        "name": str(item.get("name") or ""),
                        "size": item.get("size"),
                        "modified_at": str(item.get("modified_at") or ""),
                        "digest": str(item.get("digest") or ""),
                    }
                )
        else:
            for item in raw_models:
                if not isinstance(item, dict):
                    continue
                models.append(
                    {
                        "name": str(item.get("id") or item.get("name") or ""),
                    }
                )
        payload["reachable"] = True
        payload["models"] = [item for item in models if item.get("name")]
        return payload
    except Exception as exc:
        payload["error"] = str(exc)
        return payload


def warmup_backend_model(
    *,
    model: str,
    keep_alive: str = "",
    timeout: float = 20.0,
) -> dict[str, Any]:
    runtime = resolve_runtime()
    normalized_model = str(model or "").strip()
    payload = {
        "backend": runtime.backend,
        "provider": runtime.provider,
        "endpoint": runtime.endpoint,
        "model": normalized_model,
        "warmed": False,
        "error": "",
    }

    if not normalized_model:
        payload["error"] = "model_missing"
        return payload
    if runtime.backend != "ollama":
        payload["error"] = "warmup_supported_only_for_ollama"
        return payload

    import requests

    endpoint = str(runtime.endpoint).rstrip("/")
    if not endpoint:
        payload["error"] = "backend_endpoint_missing"
        return payload

    body = {
        "model": normalized_model,
        "prompt": "",
        "stream": False,
        "keep_alive": keep_alive or os.getenv("SOCC_OLLAMA_KEEP_ALIVE", "15m"),
    }
    try:
        response = requests.post(f"{endpoint}/api/generate", json=body, timeout=timeout)
        response.raise_for_status()
        payload["warmed"] = True
        return payload
    except Exception as exc:
        payload["error"] = str(exc)
        return payload


def benchmark_concurrency(concurrency: int = 4, hold_ms: int = 150) -> dict[str, Any]:
    runtime = resolve_runtime()
    workers = max(1, concurrency)
    hold_seconds = max(0, hold_ms) / 1000
    output: "queue.Queue[dict[str, Any]]" = queue.Queue()

    def worker(idx: int) -> None:
        started = time.perf_counter()
        with inference_guard(runtime) as (allowed, reason):
            if allowed:
                time.sleep(hold_seconds)
            output.put(
                {
                    "worker": idx,
                    "allowed": allowed,
                    "reason": reason,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            )

    threads = [threading.Thread(target=worker, args=(idx,), daemon=True) for idx in range(workers)]
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    items = sorted([output.get() for _ in range(workers)], key=lambda item: item["worker"])
    allowed = [item for item in items if item["allowed"]]
    blocked = [item for item in items if not item["allowed"]]
    reasons: dict[str, int] = {}
    for item in blocked:
        reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1

    return {
        "requested_concurrency": workers,
        "hold_ms": hold_ms,
        "total_elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "allowed_count": len(allowed),
        "blocked_count": len(blocked),
        "blocked_reasons": reasons,
        "workers": items,
    }


def benchmark_runtime(
    *,
    concurrency: int = 4,
    hold_ms: int = 150,
    include_probe: bool = True,
) -> dict[str, Any]:
    report = {
        "status": runtime_status(),
        "concurrency_benchmark": benchmark_concurrency(concurrency=concurrency, hold_ms=hold_ms),
        "streaming": {
            "api_streaming_supported": True,
            "modes": ["sse", "ollama_chunked", "backend_passthrough"],
            "notes": "O chat expõe SSE; backends locais priorizados incluem Ollama, LM Studio, vLLM e outros endpoints OpenAI-compatible.",
        },
    }
    if include_probe:
        report["probe"] = probe_inference_backend()
    return report
