"""Interactive doctor for ``socc doctor``.

Displays a categorized checklist of runtime health, allows expanding
details per category, and suggests actionable fixes.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from socc.cli.prompt_runtime import (
    confirm,
    error,
    is_interactive,
    select,
    success,
    warning,
)


# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------

_CATEGORY_ORDER = [
    "paths",
    "checks",
    "runtime",
    "knowledge_base",
    "vantage",
    "features",
    "security",
    "probe",
]

_CATEGORY_LABELS = {
    "paths": "Caminhos do Runtime",
    "checks": "Verificações de Integridade",
    "runtime": "Backend de Inferência",
    "knowledge_base": "Base de Conhecimento",
    "vantage": "Vantage API",
    "features": "Feature Flags",
    "security": "Segurança",
    "probe": "Probe do Backend",
}


# ---------------------------------------------------------------------------
# Health evaluation
# ---------------------------------------------------------------------------

def _evaluate_category(category: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Return {status, items, fixes} for a category."""
    items: list[dict[str, str]] = []
    fixes: list[str] = []
    status = "ok"

    if category == "paths":
        paths = payload.get("paths", {})
        for key in ("runtime_home", "agent_home", "env_file", "manifest_file", "intel_registry", "intel_index"):
            val = paths.get(key, "")
            exists = Path(val).exists() if val else False
            items.append({"key": key, "value": str(val) or "-", "ok": exists})
            if not exists and key in ("runtime_home", "agent_home"):
                fixes.append(f"socc init  # criar {key}")
                status = "error"
            elif not exists and key == "env_file":
                fixes.append("socc onboard  # gerar .env")
                status = "warn" if status != "error" else status

    elif category == "checks":
        checks = payload.get("checks", {})
        for key, val in sorted(checks.items()):
            items.append({"key": key, "value": str(val), "ok": bool(val)})
            if not val:
                status = "warn" if status != "error" else status
                if "runtime_home" in key:
                    fixes.append("socc init")
                    status = "error"
                elif "env_file" in key:
                    fixes.append("socc onboard")
                elif "agent_home" in key:
                    fixes.append("socc init --force")
                    status = "error"
                elif "intel" in key:
                    fixes.append("socc intel add-source --id minha-kb --name 'Base Local' --path /caminho")

    elif category == "runtime":
        rt = ((payload.get("runtime", {}) or {}).get("runtime", {}) or {})
        for key in ("enabled", "backend", "backend_label", "provider", "model", "device",
                     "gpu_available", "fallback_provider", "max_concurrency"):
            val = rt.get(key, "")
            ok = True
            if key == "enabled" and not val:
                ok = False
                status = "error"
                fixes.append("socc configure set SOCC_INFERENCE_BACKEND ollama")
            if key == "model" and not val:
                ok = False
                status = "warn" if status != "error" else status
                fixes.append("socc models set MODEL --balanced")
            items.append({"key": key, "value": str(val), "ok": ok})

    elif category == "knowledge_base":
        intel = payload.get("intel", {})
        docs = intel.get("indexed_documents", 0)
        chunks = intel.get("indexed_chunks", 0)
        items.append({"key": "index_version", "value": str(intel.get("version", "-")), "ok": True})
        items.append({"key": "indexed_documents", "value": str(docs), "ok": docs > 0})
        items.append({"key": "indexed_chunks", "value": str(chunks), "ok": chunks > 0})
        if docs == 0:
            status = "warn"
            fixes.append("socc intel add-source --id kb --name 'SOPs' --path /caminho && socc intel ingest --source-id kb")

    elif category == "vantage":
        vantage = payload.get("vantage", {})
        enabled = vantage.get("enabled", False)
        configured = vantage.get("configured", False)
        items.append({"key": "enabled", "value": str(enabled), "ok": True})
        items.append({"key": "configured", "value": str(configured), "ok": configured or not enabled})
        items.append({"key": "base_url", "value": str(vantage.get("base_url", "-")), "ok": True})
        items.append({"key": "auth_mode", "value": str(vantage.get("auth_mode", "-")), "ok": True})
        modules = vantage.get("selected_modules", [])
        items.append({"key": "selected_modules", "value": ", ".join(modules) or "-", "ok": True})
        if enabled and not configured:
            status = "warn"
            fixes.append("socc configure set SOCC_VANTAGE_BASE_URL https://...")

    elif category == "features":
        features = payload.get("features", {})
        for key, val in sorted(features.items()):
            items.append({"key": key, "value": str(val), "ok": True})

    elif category == "security":
        rt = ((payload.get("runtime", {}) or {}).get("safety", {}) or {})
        items.append({"key": "log_redaction_enabled", "value": str(rt.get("log_redaction_enabled", "-")), "ok": True})
        items.append({"key": "prompt_audit_enabled", "value": str(rt.get("prompt_audit_enabled", "-")), "ok": True})
        items.append({"key": "prompt_preview_chars", "value": str(rt.get("prompt_preview_chars", "-")), "ok": True})

    elif category == "probe":
        probe = payload.get("probe", {})
        if not probe:
            items.append({"key": "probe", "value": "não executado", "ok": True})
            return {"status": "skip", "items": items, "fixes": fixes}
        reachable = probe.get("reachable", False)
        items.append({"key": "reachable", "value": str(reachable), "ok": reachable})
        items.append({"key": "latency_ms", "value": str(probe.get("latency_ms", "-")), "ok": True})
        probe_error = probe.get("error", "")
        if probe_error:
            items.append({"key": "error", "value": str(probe_error), "ok": False})
        if not reachable:
            status = "error"
            fixes.append("Verificar se o backend está rodando (ex: `ollama serve`)")

    return {"status": status, "items": items, "fixes": fixes}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_STATUS_MARKS = {
    "ok": "OK",
    "warn": "!!",
    "error": "XX",
    "skip": "--",
}


def _print_checklist(evaluations: dict[str, dict[str, Any]]) -> None:
    """Print the summary checklist."""
    print("\nSOCC Doctor — Checklist de Saúde\n")
    for idx, cat in enumerate(_CATEGORY_ORDER):
        if cat not in evaluations:
            continue
        ev = evaluations[cat]
        mark = _STATUS_MARKS.get(ev["status"], "??")
        label = _CATEGORY_LABELS.get(cat, cat)
        print(f"  [{mark}] {idx + 1}. {label}")
    print()


def _print_category_detail(cat: str, ev: dict[str, Any]) -> None:
    """Expand a single category with item details and fixes."""
    label = _CATEGORY_LABELS.get(cat, cat)
    print(f"\n--- {label} ---\n")
    for item in ev.get("items", []):
        mark = "OK" if item.get("ok") else "--"
        print(f"  [{mark}] {item['key']}: {item['value']}")
    fixes = ev.get("fixes", [])
    if fixes:
        print("\n  Correções sugeridas:")
        for fix in fixes:
            print(f"    $ {fix}")
    print()


# ---------------------------------------------------------------------------
# Fix applicator
# ---------------------------------------------------------------------------

def _try_apply_fix(fix: str) -> bool:
    """Attempt to apply a simple fix command. Returns True if applied."""
    # Only auto-apply safe commands
    safe_prefixes = ("socc init", "socc configure set", "socc intel add-source")
    if not any(fix.startswith(prefix) for prefix in safe_prefixes):
        return False

    try:
        import subprocess
        result = subprocess.run(
            fix.split(),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            success(f"Correção aplicada: {fix}")
            return True
        else:
            warning(f"Correção falhou: {result.stderr.strip()}")
            return False
    except Exception as exc:
        warning(f"Erro ao aplicar: {exc}")
        return False


# ---------------------------------------------------------------------------
# Main interactive doctor
# ---------------------------------------------------------------------------

def run_interactive_doctor(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the interactive doctor experience."""
    if not is_interactive():
        return {"interactive": False}

    # Evaluate all categories
    evaluations: dict[str, dict[str, Any]] = {}
    for cat in _CATEGORY_ORDER:
        evaluations[cat] = _evaluate_category(cat, payload)

    # Overall status
    statuses = [ev["status"] for ev in evaluations.values()]
    if "error" in statuses:
        overall = "error"
    elif "warn" in statuses:
        overall = "warn"
    else:
        overall = "ok"

    # Print checklist
    _print_checklist(evaluations)

    overall_msg = {
        "ok": "Ambiente saudável.",
        "warn": "Ambiente funcional com avisos.",
        "error": "Problemas encontrados que precisam de atenção.",
    }
    print(f"  Status geral: [{_STATUS_MARKS[overall]}] {overall_msg.get(overall, '')}\n")

    # Collect all fixes
    all_fixes: list[str] = []
    for ev in evaluations.values():
        all_fixes.extend(ev.get("fixes", []))

    # Interactive navigation
    categories_with_issues = [
        cat for cat in _CATEGORY_ORDER
        if cat in evaluations and evaluations[cat]["status"] in ("warn", "error")
    ]

    while True:
        nav_options = ["Ver detalhes de uma categoria"]
        if all_fixes:
            nav_options.append(f"Aplicar correções ({len(all_fixes)} sugestão(ões))")
        nav_options.append("Sair")

        chosen = select("O que deseja fazer?", nav_options)

        if chosen == "Sair":
            break

        if chosen.startswith("Aplicar"):
            for fix in all_fixes:
                print(f"\n  Correção: $ {fix}")
                if confirm("  Aplicar?", default=False):
                    _try_apply_fix(fix)
            break

        if chosen.startswith("Ver detalhes"):
            cat_labels = [
                f"{_CATEGORY_LABELS.get(cat, cat)} [{_STATUS_MARKS[evaluations[cat]['status']]}]"
                for cat in _CATEGORY_ORDER if cat in evaluations
            ]
            cat_labels.append("Voltar")
            detail_choice = select("Qual categoria expandir?", cat_labels)

            if detail_choice == "Voltar":
                continue

            # Find the category key from the label
            for cat in _CATEGORY_ORDER:
                label_with_status = f"{_CATEGORY_LABELS.get(cat, cat)} [{_STATUS_MARKS[evaluations[cat]['status']]}]"
                if label_with_status == detail_choice:
                    _print_category_detail(cat, evaluations[cat])

                    # Offer fixes for this category
                    cat_fixes = evaluations[cat].get("fixes", [])
                    if cat_fixes and confirm("Aplicar correções desta categoria?", default=False):
                        for fix in cat_fixes:
                            print(f"  $ {fix}")
                            if confirm("  Executar?", default=False):
                                _try_apply_fix(fix)
                    break

    return {
        "interactive": True,
        "overall_status": overall,
        "categories": {
            cat: {"status": ev["status"], "issues": len(ev.get("fixes", []))}
            for cat, ev in evaluations.items()
        },
    }
