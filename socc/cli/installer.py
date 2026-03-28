from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import sys


RUNTIME_DIRS = ("sessions", "logs", "cache", "mcp", "prompts", "workspace", "intel")
SEED_AGENT_DIRNAME = "soc-copilot"
RUNTIME_LAYOUTS = {"checkout", "package"}


def package_root() -> Path:
    return Path(__file__).resolve().parents[2].resolve()


def resolve_runtime_layout(layout: str | None = None) -> str:
    raw = str(layout or os.getenv("SOCC_INSTALL_LAYOUT", "") or "").strip().lower()
    if raw in RUNTIME_LAYOUTS:
        return raw
    return "checkout"


def runtime_home(home: Path | None = None) -> Path:
    explicit = home
    if explicit is None:
        env_home = os.getenv("SOCC_HOME", "").strip()
        if env_home:
            explicit = Path(env_home)
    return (explicit or Path.home() / ".socc").expanduser()


def runtime_workspace(home: Path | None = None) -> Path:
    return runtime_home(home) / "workspace"


def runtime_checkout_link(home: Path | None = None) -> Path:
    return runtime_home(home) / "project"


def runtime_project_link(home: Path | None = None) -> Path:
    return runtime_workspace(home) / "project"


def runtime_agent_home(home: Path | None = None) -> Path:
    return runtime_workspace(home) / SEED_AGENT_DIRNAME


def runtime_bin_dir(home: Path | None = None) -> Path:
    return runtime_home(home) / "bin"


def runtime_venv_dir(home: Path | None = None) -> Path:
    return runtime_home(home) / "venv"


def runtime_logs_dir(home: Path | None = None) -> Path:
    return runtime_home(home) / "logs"


def runtime_service_pid_path(home: Path | None = None) -> Path:
    return runtime_logs_dir(home) / "socc-serve.pid"


def runtime_service_meta_path(home: Path | None = None) -> Path:
    return runtime_logs_dir(home) / "socc-serve.json"


def runtime_service_stdout_path(home: Path | None = None) -> Path:
    return runtime_logs_dir(home) / "socc-serve.out.log"


def runtime_service_stderr_path(home: Path | None = None) -> Path:
    return runtime_logs_dir(home) / "socc-serve.err.log"


def write_cli_launcher(
    home: Path | None = None,
    *,
    python_executable: str | None = None,
    fallback_python_executable: str | None = None,
    project_root: Path | None = None,
    force: bool = False,
) -> Path:
    base_dir = runtime_home(home)
    bin_dir = runtime_bin_dir(base_dir)
    bin_dir.mkdir(parents=True, exist_ok=True)
    launcher_path = bin_dir / "socc"
    if launcher_path.exists() and not force:
        return launcher_path

    python_cmd = python_executable or sys.executable
    fallback_python_cmd = fallback_python_executable or sys.executable
    source_root = (project_root or Path(__file__).resolve().parents[2]).resolve()
    launcher = "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            f'SOCC_HOME="${{SOCC_HOME:-{base_dir}}}"',
            f'SOCC_PROJECT_ROOT="${{SOCC_PROJECT_ROOT:-{source_root}}}"',
            f'VENV_PY_DEFAULT="{python_cmd}"',
            f'FALLBACK_PY_DEFAULT="{fallback_python_cmd}"',
            'if [[ -n "${SOCC_PYTHON:-}" ]]; then',
            '  PYTHON_BIN="$SOCC_PYTHON"',
            'elif "$VENV_PY_DEFAULT" -c "import socc.cli.main" >/dev/null 2>&1; then',
            '  PYTHON_BIN="$VENV_PY_DEFAULT"',
            'else',
            '  PYTHON_BIN="$FALLBACK_PY_DEFAULT"',
            'fi',
            'export PYTHONPATH="$SOCC_PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"',
            'exec "$PYTHON_BIN" -m socc.cli.main "$@"',
            "",
        ]
    )
    launcher_path.write_text(launcher, encoding="utf-8")
    launcher_path.chmod(launcher_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return launcher_path


def _seed_agent_workspace(base_dir: Path, force: bool = False) -> tuple[Path, bool]:
    repo_root = Path(__file__).resolve().parents[2]
    source_agent = repo_root / ".agents" / SEED_AGENT_DIRNAME
    target_agent = base_dir / "workspace" / SEED_AGENT_DIRNAME

    if not source_agent.exists():
        return target_agent, False

    if force and target_agent.exists():
        shutil.rmtree(target_agent)

    if not target_agent.exists():
        shutil.copytree(source_agent, target_agent)
        return target_agent, True

    # Atualiza somente arquivos ausentes para preservar customizações locais.
    for source_path in source_agent.rglob("*"):
        if not source_path.is_file():
            continue
        relative = source_path.relative_to(source_agent)
        target_path = target_agent / relative
        if not target_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, target_path)

    return target_agent, False


def _seed_project_link(base_dir: Path, force: bool = False) -> tuple[Path, bool]:
    repo_root = package_root()
    targets = (
        runtime_checkout_link(base_dir),
        runtime_project_link(base_dir),
    )
    linked_any = False

    for target in targets:
        if force and (target.is_symlink() or target.exists()):
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)

        if target.is_symlink():
            try:
                if target.resolve() == repo_root:
                    continue
            except Exception:
                target.unlink(missing_ok=True)

        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                target.symlink_to(repo_root, target_is_directory=True)
                linked_any = True
            except Exception:
                target.write_text(str(repo_root) + "\n", encoding="utf-8")
                linked_any = True

    return runtime_checkout_link(base_dir), linked_any


def _clear_project_links(base_dir: Path) -> None:
    for target in (runtime_checkout_link(base_dir), runtime_project_link(base_dir)):
        if target.is_symlink() or target.is_file():
            target.unlink(missing_ok=True)
        elif target.is_dir():
            shutil.rmtree(target)

def _write_runtime_manifest(
    base_dir: Path,
    *,
    layout: str,
    force: bool = False,
) -> Path:
    manifest_path = base_dir / "socc.json"
    if manifest_path.exists() and not force:
        return manifest_path

    source_root = package_root()
    checkout_link = runtime_checkout_link(base_dir)
    project_link = runtime_project_link(base_dir)
    include_checkout_links = layout == "checkout"
    manifest = {
        "meta": {
            "runtime": "socc",
            "version": "0.1.0",
            "installation_layout": layout,
        },
        "paths": {
            "runtime_home": str(base_dir),
            "bin_dir": str(base_dir / "bin"),
            "venv_dir": str(base_dir / "venv"),
            "cli_launcher": str(base_dir / "bin" / "socc"),
            "workspace": str(base_dir / "workspace"),
            "checkout_link": str(checkout_link) if include_checkout_links else "",
            "agent_home": str(base_dir / "workspace" / SEED_AGENT_DIRNAME),
            "project_link": str(project_link) if include_checkout_links else "",
            "source_checkout": str(source_root) if include_checkout_links else "",
            "package_root": str(source_root),
            "env_file": str(base_dir / ".env"),
            "logs": str(base_dir / "logs"),
            "service_pid": str(runtime_service_pid_path(base_dir)),
            "service_meta": str(runtime_service_meta_path(base_dir)),
            "service_stdout": str(runtime_service_stdout_path(base_dir)),
            "service_stderr": str(runtime_service_stderr_path(base_dir)),
            "sessions": str(base_dir / "sessions"),
            "intel_home": str(base_dir / "intel"),
            "intel_registry": str(base_dir / "intel" / "sources.json"),
            "intel_index": str(base_dir / "intel" / "index" / "index.jsonl"),
        },
        "agent": {
            "default_workspace": str(base_dir / "workspace" / SEED_AGENT_DIRNAME),
            "override_env": "SOCC_AGENT_HOME",
        },
        "models": {
            "provider_env": "LLM_PROVIDER",
            "model_env": "LLM_MODEL",
            "device_env": "SOCC_INFERENCE_DEVICE",
            "fallback_env": "SOCC_LLM_FALLBACK_PROVIDER",
        },
        "features": {
            "analyze_api_env": "SOCC_FEATURE_ANALYZE_API",
            "draft_api_env": "SOCC_FEATURE_DRAFT_API",
            "chat_api_env": "SOCC_FEATURE_CHAT_API",
            "chat_streaming_env": "SOCC_FEATURE_CHAT_STREAMING",
            "feedback_api_env": "SOCC_FEATURE_FEEDBACK_API",
            "export_api_env": "SOCC_FEATURE_EXPORT_API",
            "threat_intel_env": "SOCC_FEATURE_THREAT_INTEL",
            "runtime_api_env": "SOCC_FEATURE_RUNTIME_API",
        },
        "rag": {
            "chunk_chars_env": "SOCC_RAG_CHUNK_CHARS",
            "chunk_overlap_env": "SOCC_RAG_CHUNK_OVERLAP",
            "max_file_bytes_env": "SOCC_RAG_MAX_FILE_BYTES",
        },
        "safety": {
            "log_redaction_env": "SOCC_LOG_REDACTION_ENABLED",
            "prompt_audit_env": "SOCC_PROMPT_AUDIT_ENABLED",
            "prompt_preview_chars_env": "SOCC_PROMPT_PREVIEW_CHARS",
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def bootstrap_runtime(
    home: Path | None = None,
    force: bool = False,
    layout: str | None = None,
) -> dict[str, str]:
    base_dir = runtime_home(home)
    base_dir.mkdir(parents=True, exist_ok=True)
    resolved_layout = resolve_runtime_layout(layout)

    created_dirs: list[str] = []
    for dirname in RUNTIME_DIRS:
        path = base_dir / dirname
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(path))

    repo_root = Path(__file__).resolve().parents[2]
    source_env = repo_root / ".env.example"
    target_env = base_dir / ".env"
    target_env_example = base_dir / ".env.example"

    if source_env.exists():
        if force or not target_env_example.exists():
            shutil.copyfile(source_env, target_env_example)
        if force or not target_env.exists():
            shutil.copyfile(source_env, target_env)

    agent_home, workspace_seeded = _seed_agent_workspace(base_dir, force=force)
    if resolved_layout == "checkout":
        project_link, project_linked = _seed_project_link(base_dir, force=force)
    else:
        project_link = runtime_checkout_link(base_dir)
        project_linked = False
        if force:
            _clear_project_links(base_dir)
    manifest_path = _write_runtime_manifest(base_dir, layout=resolved_layout, force=force)
    from socc.core.knowledge_base import ensure_knowledge_base

    ensure_knowledge_base(base_dir)
    launcher_path = write_cli_launcher(
        base_dir,
        project_root=package_root(),
        force=force,
    )

    readme_path = base_dir / "README.txt"
    if force or not readme_path.exists():
        readme_path.write_text(
            "\n".join(
                [
                    "SOCC runtime home",
                    "",
                    "- sessions/: local artifacts and chat exports",
                    "- logs/: local runtime logs",
                    "- cache/: temporary caches",
                    "- mcp/: MCP local state",
                    "- prompts/: prompt overrides",
                    "- intel/: source registry, normalized documents, and local RAG index",
                    "- bin/: launcher scripts for the local runtime",
                    "- workspace/: runtime-local agent workspace inspired by OpenClaw",
                    "",
                    "Edit .env to override local runtime settings.",
                    f"Set SOCC_AGENT_HOME={agent_home} to force a specific agent workspace.",
                    f"Installation layout: {resolved_layout}",
                    f"Package root: {package_root()}",
                    (
                        f"Workspace project link: {project_link}"
                        if resolved_layout == "checkout"
                        else "Code, templates and assets stay in the installed package; the runtime home keeps only user state and the agent workspace."
                    ),
                    "Use `socc intel add-source` and `socc intel ingest` to seed the local knowledge base.",
                    f"Local launcher: {launcher_path}",
                ]
            ),
            encoding="utf-8",
        )

    return {
        "runtime_home": str(base_dir),
        "env_file": str(target_env),
        "agent_home": str(agent_home),
        "manifest_file": str(manifest_path),
        "launcher_file": str(launcher_path),
        "layout": resolved_layout,
        "package_root": str(package_root()),
        "workspace_seeded": "yes" if workspace_seeded else "no",
        "project_linked": "yes" if project_linked else "no",
        "created_dirs": ", ".join(created_dirs) if created_dirs else "",
    }
