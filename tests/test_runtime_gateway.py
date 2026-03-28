"""
Valida status do runtime e registro de eventos de inferencia.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from socc.gateway.llm_gateway import (
    benchmark_runtime,
    metrics_summary,
    probe_inference_backend,
    record_analysis_event,
    record_inference_event,
    record_prompt_audit,
    resolve_runtime,
    supported_backends_payload,
    runtime_status,
)
from socc.utils.safety import redact_sensitive_text

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


try:
    cfg = resolve_runtime()
    check("runtime_has_provider", bool(cfg.provider))
    check("runtime_has_backend", bool(cfg.backend))
    check("runtime_has_device", cfg.device in {"gpu", "cpu", "remote"} or bool(cfg.device))

    record_inference_event(
        source="test-suite",
        provider=cfg.provider,
        model=cfg.model,
        requested_device=cfg.device,
        effective_device=cfg.device,
        latency_ms=123.4,
        success=True,
        fallback_used=False,
    )
    record_inference_event(
        source="test-suite",
        provider=cfg.provider,
        model=cfg.model,
        requested_device=cfg.device,
        effective_device="cpu",
        latency_ms=456.7,
        success=False,
        fallback_used=True,
        error="simulated_failure token=abc123 from 203.0.113.8",
    )
    record_analysis_event(
        source="test-suite",
        latency_ms=87.5,
        success=True,
        schema_valid=True,
        threat_intel_used=True,
        payload_hash="abc123",
    )
    record_analysis_event(
        source="test-suite",
        latency_ms=42.0,
        success=False,
        schema_valid=False,
        error="email analyst@example.com from 198.51.100.7",
    )
    prompt_audit = record_prompt_audit(
        source="test-suite",
        provider=cfg.provider,
        model=cfg.model,
        prompt_text="Contato analyst@example.com ip 198.51.100.7 url https://example.org/token",
        skill="payload-triage",
    )
    metrics = metrics_summary()
    status = runtime_status()
    benchmark = benchmark_runtime(concurrency=3, hold_ms=10, include_probe=False)
    catalog = supported_backends_payload()

    check("metrics_total_events", metrics.get("total_events", 0) >= 2)
    check("metrics_fallback_count", metrics.get("fallback_count", 0) >= 1)
    check("metrics_error_redacted", "[redacted-ip]" in ((metrics.get("last_event") or {}).get("error") or ""))
    check("analysis_metrics_present", "analysis_pipeline" in metrics)
    check("analysis_schema_invalid_count", (metrics.get("analysis_pipeline") or {}).get("schema_invalid_count", 0) >= 1)
    check("runtime_status_has_resources", "resources" in status and "metrics" in status)
    check("runtime_status_has_backend_catalog", "backends" in status and (status.get("backends") or {}).get("supported"))
    check("runtime_status_has_cpu", "cpu" in (status.get("resources") or {}))
    check("runtime_status_has_safety", "safety" in status and "log_redaction_enabled" in status["safety"])
    check("runtime_backend_catalog_count", len(catalog) >= 5)
    check("runtime_backend_catalog_has_ollama", any(item.get("key") == "ollama" for item in catalog))
    check("benchmark_has_concurrency", "concurrency_benchmark" in benchmark)
    check("benchmark_streaming_declared", "streaming" in benchmark and "api_streaming_supported" in benchmark["streaming"])
    check("prompt_audit_redacted_preview", "[redacted-email]" in str(prompt_audit.get("preview", "")))
    check("redact_sensitive_text_masks_url", "[redacted-url]" in redact_sensitive_text("https://example.org/demo"))

    original_backend = os.environ.get("SOCC_INFERENCE_BACKEND")
    original_compat = os.environ.get("SOCC_OPENAI_COMPAT_URL")
    original_lmstudio = os.environ.get("SOCC_LMSTUDIO_URL")
    try:
        os.environ["SOCC_INFERENCE_BACKEND"] = "lmstudio"
        os.environ["SOCC_LMSTUDIO_URL"] = "http://127.0.0.1:1234/v1"
        lmstudio_cfg = resolve_runtime()
        check("runtime_explicit_lmstudio_backend", lmstudio_cfg.backend == "lmstudio")
        check("runtime_explicit_lmstudio_provider", lmstudio_cfg.provider == "openai-compatible")
        check("runtime_explicit_lmstudio_device_local", lmstudio_cfg.device in {"gpu", "cpu"})

        os.environ["SOCC_INFERENCE_BACKEND"] = "openai-compatible"
        os.environ["SOCC_OPENAI_COMPAT_URL"] = ""
        compat_probe = probe_inference_backend()
        check("runtime_openai_compat_probe_missing_endpoint", compat_probe.get("error") == "backend_endpoint_missing")
    finally:
        if original_backend is None:
            os.environ.pop("SOCC_INFERENCE_BACKEND", None)
        else:
            os.environ["SOCC_INFERENCE_BACKEND"] = original_backend
        if original_compat is None:
            os.environ.pop("SOCC_OPENAI_COMPAT_URL", None)
        else:
            os.environ["SOCC_OPENAI_COMPAT_URL"] = original_compat
        if original_lmstudio is None:
            os.environ.pop("SOCC_LMSTUDIO_URL", None)
        else:
            os.environ["SOCC_LMSTUDIO_URL"] = original_lmstudio
except Exception as exc:
    check("runtime_gateway_flow", False, str(exc))


print(f"\n{'='*60}")
print(f"SOCC Runtime — Gateway + Metrics  ({len(resultados)} checks)")
print("="*60)
falhas = [(n, d) for s, n, d in resultados if s == FAIL]
aprovados = len(resultados) - len(falhas)
print(f"  Aprovados : {aprovados}/{len(resultados)}")
print(f"  Falhas    : {len(falhas)}/{len(resultados)}")
print()
for nome, detalhe in falhas:
    extra = f" — {detalhe}" if detalhe else ""
    print(f"  FALHA: {nome}{extra}")
if not falhas:
    print("  Todos os checks passaram.")
print()

sys.exit(1 if falhas else 0)
