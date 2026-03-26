from __future__ import annotations

from pathlib import Path
import shutil


RUNTIME_DIRS = ("sessions", "logs", "cache", "mcp", "prompts")


def runtime_home(home: Path | None = None) -> Path:
    return (home or Path.home() / ".socc").expanduser()


def bootstrap_runtime(home: Path | None = None, force: bool = False) -> dict[str, str]:
    base_dir = runtime_home(home)
    base_dir.mkdir(parents=True, exist_ok=True)

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
                    "",
                    "Edit .env to override local runtime settings.",
                ]
            ),
            encoding="utf-8",
        )

    return {
        "runtime_home": str(base_dir),
        "env_file": str(target_env),
        "created_dirs": ", ".join(created_dirs) if created_dirs else "",
    }
