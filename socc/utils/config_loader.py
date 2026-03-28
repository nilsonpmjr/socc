from __future__ import annotations

from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - ambiente mínimo sem dependências
    def load_dotenv(*_args, **_kwargs) -> bool:
        return False


def repo_env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def runtime_env_path() -> Path:
    return Path.home().expanduser() / ".socc" / ".env"


def load_environment() -> dict[str, str]:
    runtime_env = runtime_env_path()
    repo_env = repo_env_path()

    if runtime_env.exists():
        load_dotenv(runtime_env, override=False)
    if repo_env.exists():
        load_dotenv(repo_env, override=False)

    return {
        "runtime_env": str(runtime_env),
        "repo_env": str(repo_env),
    }
