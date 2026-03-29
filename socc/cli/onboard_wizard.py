"""Interactive onboarding wizard for ``socc onboard``.

Guides the user through 12 configuration steps, collecting settings and
persisting them in ``~/.socc/.env`` via :func:`batch_update_env`.

Uses Rich for a modern, interactive TUI experience.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from socc.cli.prompt_runtime import (
    ask,
    ask_path,
    ask_secret,
    checklist,
    confirm,
    error,
    is_interactive,
    select,
    skip,
    step,
    success,
    summary,
    warning,
)
from socc.gateway.llm_gateway import detect_gpu_hardware

TOTAL_STEPS = 12

# ---------------------------------------------------------------------------
# Rich UI helpers
# ---------------------------------------------------------------------------

def _get_console():
    try:
        from rich.console import Console
        return Console()
    except ImportError:
        return None


def _banner():
    console = _get_console()
    if not console:
        print("\n" + "=" * 58)
        print("  SOCC — Wizard de Onboarding")
        print("=" * 58)
        print("Pressione Ctrl+C a qualquer momento para cancelar.\n")
        return
    try:
        from rich.panel import Panel
        from rich.text import Text
        from rich.align import Align
        title = Text()
        title.append("⚡ SOCC", style="bold cyan")
        title.append(" — SOC Copilot", style="bold white")
        subtitle = Text("Configure seu runtime local de IA para SOC", style="dim")
        content = Align.center(title) 
        console.print()
        console.print(Panel(
            f"[bold cyan]⚡ SOCC[/bold cyan] [bold white]SOC Copilot[/bold white]\n\n"
            "[dim]Configure seu runtime local de IA para SOC[/dim]\n"
            "[dim]Pressione Ctrl+C a qualquer momento para cancelar[/dim]",
            border_style="cyan",
            padding=(1, 4),
        ))
        console.print()
    except Exception:
        print("\n" + "=" * 58)
        print("  SOCC — Wizard de Onboarding")
        print("=" * 58)


def _section_header(num: int, total: int, title: str):
    console = _get_console()
    if not console:
        step(num, total, title)
        return
    try:
        from rich.rule import Rule
        pct = int((num / total) * 100)
        bar_filled = int(pct / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        console.print()
        console.print(Rule(
            f"[bold cyan][{num}/{total}][/bold cyan] [bold white]{title}[/bold white]  "
            f"[dim cyan]{bar}[/dim cyan] [dim]{pct}%[/dim]",
            style="cyan",
        ))
    except Exception:
        step(num, total, title)


def _ok(msg: str):
    console = _get_console()
    if console:
        console.print(f"  [bold green]✓[/bold green] {msg}")
    else:
        success(msg)


def _warn(msg: str):
    console = _get_console()
    if console:
        console.print(f"  [bold yellow]⚠[/bold yellow]  {msg}")
    else:
        warning(msg)


def _err(msg: str):
    console = _get_console()
    if console:
        console.print(f"  [bold red]✗[/bold red]  {msg}")
    else:
        error(msg)


def _info(msg: str):
    console = _get_console()
    if console:
        console.print(f"  [dim]{msg}[/dim]")
    else:
        print(f"  {msg}")


def _probe_spinner(label: str, fn) -> Any:
    """Run fn() with an animated spinner. Returns fn()'s result."""
    console = _get_console()
    if not console:
        return fn()
    try:
        from rich.live import Live
        from rich.spinner import Spinner
        from rich.text import Text
        result_box: list[Any] = [None]

        def _run():
            result_box[0] = fn()

        import threading
        t = threading.Thread(target=_run, daemon=True)
        t.start()

        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        i = 0
        while t.is_alive():
            console.print(f"  [cyan]{frames[i % len(frames)]}[/cyan] [dim]{label}...[/dim]", end="\r")
            time.sleep(0.08)
            i += 1
        t.join()
        console.print(" " * 60, end="\r")  # clear line
        return result_box[0]
    except Exception:
        return fn()


def _print_table(rows: list[tuple[str, str]]):
    console = _get_console()
    if not console:
        for k, v in rows:
            print(f"  {k}: {v}")
        return
    try:
        from rich.table import Table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="dim cyan", no_wrap=True)
        table.add_column(style="white")
        for k, v in rows:
            # Mask secrets
            display_v = v
            if any(s in k.lower() for s in ("key", "token", "pass", "secret")):
                display_v = v[:8] + "****" + v[-4:] if len(v) > 12 else "****"
            table.add_row(k, display_v)
        console.print(table)
    except Exception:
        for k, v in rows:
            print(f"  {k}: {v}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _probe_backend_quiet(endpoint: str, backend: str) -> bool:
    try:
        import requests
        if backend == "ollama":
            resp = requests.get(endpoint, timeout=3)
            return resp.status_code < 500
        else:
            resp = requests.get(f"{endpoint}/models", timeout=3)
            return resp.status_code < 500
    except Exception:
        return False


def _list_ollama_models(endpoint: str) -> list[str]:
    try:
        import requests
        resp = requests.get(f"{endpoint}/api/tags", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            models = data.get("models", [])
            return [m.get("name", "") for m in models if m.get("name")]
    except Exception:
        pass
    return []


def _test_anthropic_credential(credential: str, auth_method: str = "api_key") -> bool:
    """Test Anthropic credential — handles both API key and OAuth token."""
    try:
        import requests
        headers = {"anthropic-version": "2023-06-01"}
        if auth_method == "oauth":
            headers["Authorization"] = f"Bearer {credential}"
            headers["anthropic-beta"] = "oauth-2025-04-20"
        else:
            headers["x-api-key"] = credential
        resp = requests.get(
            "https://api.anthropic.com/v1/models",
            headers=headers,
            timeout=8,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _detect_gpu() -> str | None:
    snapshot = detect_gpu_hardware()
    if snapshot.get("available"):
        return str(snapshot.get("label") or "").strip() or "GPU"
    return None


def _scan_candidate_kb_paths() -> list[str]:
    candidates = []
    alertas = os.environ.get("ALERTAS_ROOT", "")
    if alertas and Path(alertas).expanduser().is_dir():
        candidates.append(alertas)
    for guess in [
        "~/Documentos/Alertas",
        "~/Documents/Alertas",
        "~/Documents/SOC",
        "~/Documentos/SOC",
    ]:
        p = Path(guess).expanduser()
        if p.is_dir():
            candidates.append(str(p))
    return candidates


def _count_indexable_files(path: Path) -> int:
    exts = {".txt", ".md", ".log", ".json", ".csv", ".xml", ".yaml", ".yml", ".html"}
    count = 0
    try:
        for f in path.rglob("*"):
            if f.is_file() and f.suffix.lower() in exts:
                count += 1
    except PermissionError:
        pass
    return count


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def step_runtime_home(env: dict[str, str], current_home: Path | None) -> Path:
    _section_header(1, TOTAL_STEPS, "Runtime Home")
    default = str(current_home or "~/.socc")
    exists = Path(default).expanduser().exists()
    if exists:
        _ok(f"Runtime existente detectado em {Path(default).expanduser()}")
        if confirm("Reaproveitar runtime existente?"):
            return Path(default).expanduser()
    chosen = ask_path("Onde instalar o runtime do SOCC?", default=default) or Path(default).expanduser()
    return chosen


def _configure_one_kb_source(env: dict[str, str], index: int) -> dict[str, str] | None:
    candidates = _scan_candidate_kb_paths()
    default_path = candidates[0] if candidates and index == 0 else ""
    if candidates and index == 0:
        _info(f"Candidatos detectados: {', '.join(candidates)}")

    kb_path = ask_path("Caminho da pasta de conhecimento", default=default_path, must_exist=True)
    if not kb_path:
        return None

    file_count = _count_indexable_files(kb_path)
    _info(f"{file_count} arquivos indexáveis encontrados.")

    kind = select("Tipo de fonte:", ["document_set", "case_notes"])
    trust = select("Nível de confiança:", ["internal", "curated_external"])
    tags = ask("Tags (separadas por vírgula)", default="sop,playbook")
    ingest = file_count > 0 and confirm("Indexar agora?")

    _ok(f"Fonte adicionada: {kb_path} ({file_count} arquivos)")
    return {
        "path": str(kb_path),
        "kind": kind,
        "trust": trust,
        "tags": tags,
        "file_count": file_count,
        "ingest": ingest,
    }


def step_knowledge_base(env: dict[str, str]) -> None:
    _section_header(2, TOTAL_STEPS, "Base Local de Conhecimento")
    if not confirm("Apontar pastas de conhecimento local (SOPs, playbooks, regras)?", default=False):
        skip("Knowledge base será configurada depois.")
        return

    sources: list[dict[str, str]] = []
    while True:
        source = _configure_one_kb_source(env, len(sources))
        if source:
            sources.append(source)
        chosen = select("", ["Adicionar outra pasta", "Continuar >>"], default=1)
        if chosen.startswith("Continuar"):
            break

    if not sources:
        skip("Nenhuma fonte configurada.")
        return

    first = sources[0]
    env["ALERTAS_ROOT"] = first["path"]
    env["_KB_SOURCE_PATH"] = first["path"]
    env["_KB_SOURCE_KIND"] = first["kind"]
    env["_KB_SOURCE_TRUST"] = first["trust"]
    env["_KB_SOURCE_TAGS"] = first["tags"]
    if first.get("ingest"):
        env["_KB_INGEST_NOW"] = "true"
    if len(sources) > 1:
        import json
        env["_KB_SOURCES_JSON"] = json.dumps(sources)
    _ok(f"{len(sources)} fonte(s) de conhecimento configurada(s).")


def step_backend(env: dict[str, str]) -> None:
    _section_header(3, TOTAL_STEPS, "Backend de Inferência")

    backends_to_probe = {
        "ollama": os.environ.get("OLLAMA_URL", "http://localhost:11434"),
        "lmstudio": os.environ.get("SOCC_LMSTUDIO_URL", "http://127.0.0.1:1234/v1"),
        "vllm": os.environ.get("SOCC_VLLM_URL", "http://127.0.0.1:8000/v1"),
    }

    detected: list[str] = []
    for name, url in backends_to_probe.items():
        reachable = _probe_spinner(f"Testando {name}", lambda u=url, n=name: _probe_backend_quiet(u, n))
        if reachable:
            _ok(f"{name} em {url}")
            detected.append(name)
        else:
            _info(f"{name} em {url} — não encontrado")

    gpu_snapshot = detect_gpu_hardware()
    gpu = _detect_gpu()
    if gpu:
        _ok(f"GPU detectada: {gpu}")
    elif gpu_snapshot.get("label"):
        _warn(f"GPU sem suporte útil para Ollama: {gpu_snapshot.get('label')}. Device = cpu.")
    else:
        _warn("Nenhuma GPU detectada. Device = cpu.")

    env["SOCC_INFERENCE_DEVICE"] = "gpu" if gpu else "cpu"

    configured_backends: list[str] = list(detected)

    while True:
        options: list[str] = []
        for b in ["ollama", "lmstudio", "vllm", "openai-compatible"]:
            tag = " [configurado]" if b in configured_backends else ""
            options.append(f"{b}{tag}")
        options.append("Continuar >>")

        chosen = select("Configurar backend local:", options)
        if chosen.startswith("Continuar"):
            break

        backend_key = chosen.split(" [")[0]

        if backend_key == "ollama":
            url = ask("URL do Ollama", default=backends_to_probe.get("ollama", "http://localhost:11434"))
            env["OLLAMA_URL"] = url
            if backend_key not in configured_backends:
                configured_backends.append(backend_key)
        elif backend_key == "lmstudio":
            url = ask("URL do LM Studio", default=backends_to_probe.get("lmstudio", "http://127.0.0.1:1234/v1"))
            env["SOCC_LMSTUDIO_URL"] = url
            if backend_key not in configured_backends:
                configured_backends.append(backend_key)
        elif backend_key == "vllm":
            url = ask("URL do vLLM", default=backends_to_probe.get("vllm", "http://127.0.0.1:8000/v1"))
            env["SOCC_VLLM_URL"] = url
            if backend_key not in configured_backends:
                configured_backends.append(backend_key)
        elif backend_key == "openai-compatible":
            url = ask("URL do endpoint OpenAI-compatible", default="")
            if url:
                env["SOCC_OPENAI_COMPAT_URL"] = url
            model = ask("Modelo padrão", default="")
            if model:
                env["SOCC_OPENAI_COMPAT_MODEL"] = model
            if backend_key not in configured_backends:
                configured_backends.append(backend_key)

    # Backend primário — será complementado com providers de nuvem depois
    if configured_backends:
        all_choices = configured_backends + ["anthropic", "openai-compatible", "auto"]
        # Remove duplicatas mantendo ordem
        all_choices = list(dict.fromkeys(all_choices))
        primary = select("Backend primário:", all_choices, default=0)
    else:
        all_backends = ["ollama", "lmstudio", "vllm", "openai-compatible", "anthropic", "auto"]
        primary = select("Backend primário:", all_backends, default=0)

    env["SOCC_INFERENCE_BACKEND"] = primary
    # Priority será atualizada em step_cloud_provider quando providers de nuvem forem adicionados
    env["_LOCAL_BACKENDS"] = ",".join(configured_backends)

    _ok(f"Backend primário: {primary} (device: {'gpu' if gpu else 'cpu'})")


def step_models(env: dict[str, str]) -> None:
    _section_header(4, TOTAL_STEPS, "Seleção de Modelos Locais")

    backend = env.get("SOCC_INFERENCE_BACKEND", "ollama")
    models: list[str] = []

    if backend in ("ollama", "auto") or "ollama" in env.get("_LOCAL_BACKENDS", ""):
        endpoint = env.get("OLLAMA_URL", os.environ.get("OLLAMA_URL", "http://localhost:11434"))
        models = _probe_spinner("Listando modelos Ollama", lambda: _list_ollama_models(endpoint))
        if models:
            _info("Modelos instalados no Ollama:")
            for m in models:
                _info(f"  • {m}")
        else:
            _warn("Nenhum modelo encontrado no Ollama.")

    if models:
        fast = select("Perfil Fast (triagem rápida):", models, default=0)
        balanced_default = next(
            (i for i, m in enumerate(models) if any(s in m for s in ("9b", "7b", "8b"))),
            0,
        )
        balanced = select("Perfil Balanced (análise):", models, default=balanced_default)
        deep = select("Perfil Deep (drafts complexos):", models, default=balanced_default)
    else:
        fast = ask("Modelo Fast", default="llama3.2:3b")
        balanced = ask("Modelo Balanced", default="qwen3.5:9b")
        deep = ask("Modelo Deep", default="qwen3.5:9b")

    env["SOCC_OLLAMA_FAST_MODEL"] = fast
    env["SOCC_OLLAMA_BALANCED_MODEL"] = balanced
    env["SOCC_OLLAMA_DEEP_MODEL"] = deep
    env["OLLAMA_MODEL"] = balanced
    _ok(f"Fast={fast}  Balanced={balanced}  Deep={deep}")


def _oauth_login_with_ui(provider_name: str) -> str | None:
    try:
        from socc.cli.oauth_flow import PROVIDERS, credentials_valid, oauth_login

        provider = PROVIDERS.get(provider_name)
        if not provider:
            _warn(f"Provider OAuth desconhecido: {provider_name}")
            return None

        force_reauth = False
        if credentials_valid(provider_name):
            reuse = confirm("Credencial existente detectada. Reutilizar?", default=True)
            force_reauth = not reuse

        result = oauth_login(provider_name, force_reauth=force_reauth)

        if result.get("error"):
            _err(f"OAuth falhou: {result['error']}")
            return None

        token = result.get("access_token", "")
        if token:
            if result.get("reused"):
                _ok(f"Credencial {provider.label} reutilizada.")
            else:
                _ok(f"Login {provider.label} realizado com sucesso!")
            return token

        _warn("Nenhum token obtido.")
        return None
    except ImportError:
        _warn("Módulo oauth_flow não encontrado. Use API key manual.")
        return None
    except Exception as exc:
        _err(f"Erro no login OAuth: {exc}")
        return None


def _configure_anthropic(env: dict[str, str]) -> None:
    auth_method = select("Método de autenticação:", [
        "Login com conta (OAuth no navegador)",
        "Colar API key diretamente",
    ])
    using_oauth = auth_method.startswith("Login")

    if using_oauth:
        credential = _oauth_login_with_ui("anthropic")
        env["SOCC_AUTH_METHOD_ANTHROPIC"] = "oauth"
    else:
        credential = ask_secret("API Key Anthropic")
        env["SOCC_AUTH_METHOD_ANTHROPIC"] = "api_key"

    if not credential:
        _warn("Nenhuma credencial obtida para Anthropic.")
        return

    env["LLM_ENABLED"] = "true"
    # Só seta ANTHROPIC_API_KEY se for api_key — OAuth usa o oauth_store
    if not using_oauth:
        env["ANTHROPIC_API_KEY"] = credential

    # Não sobrescreve LLM_MODEL se já existe um modelo válido de outro provider
    current_model = env.get("LLM_MODEL", "")
    if not current_model or "gpt" in current_model.lower():
        model = ask("Modelo Anthropic", default="claude-haiku-4-5-20251001")
        env["LLM_MODEL"] = model
    else:
        model = current_model

    if not env.get("SOCC_LLM_FALLBACK_PROVIDER"):
        env["SOCC_LLM_FALLBACK_PROVIDER"] = "anthropic"

    if confirm("Testar conexão?"):
        ok = _probe_spinner(
            "Validando credencial Anthropic",
            lambda: _test_anthropic_credential(credential, "oauth" if using_oauth else "api_key"),
        )
        if ok:
            _ok("Conexão Anthropic validada.")
        else:
            _warn("Falha na validação. Verifique a credencial.")
            if using_oauth and confirm("Refazer login OAuth agora?", default=True):
                new_token = _oauth_login_with_ui("anthropic")
                if new_token:
                    retried_ok = _probe_spinner(
                        "Revalidando",
                        lambda t=new_token: _test_anthropic_credential(t, "oauth"),
                    )
                    if retried_ok:
                        _ok("Conexão OK após refazer o login.")
                    else:
                        _warn("Credencial renovada, mas API ainda não respondeu. Tente em alguns instantes.")

    _ok("Anthropic configurado.")


def _normalize_openai_endpoint(url: str, auth_method: str = "api_key") -> str:
    normalized = str(url or "").strip().rstrip("/")
    if normalized:
        if auth_method == "oauth" and normalized == "https://api.openai.com/v1":
            return "https://chatgpt.com/backend-api"
        return normalized
    if auth_method == "oauth":
        return "https://chatgpt.com/backend-api"
    return "https://api.openai.com/v1"


def _test_openai_credential(
    api_key: str,
    url: str = "https://api.openai.com/v1",
    *,
    model: str = "gpt-5-codex",
    auth_method: str = "api_key",
) -> bool:
    try:
        import requests
        effective_url = _normalize_openai_endpoint(url, auth_method)
        headers = {"Authorization": f"Bearer {api_key}"}
        if auth_method == "oauth" and "chatgpt.com/backend-api" in effective_url:
            resp = requests.post(
                f"{effective_url}/v1/responses",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model or "gpt-5-codex", "input": "ping", "max_output_tokens": 8},
                timeout=8,
            )
            return resp.status_code in {200, 201, 202, 429}
        resp = requests.get(f"{effective_url}/models", headers=headers, timeout=5)
        return resp.status_code in {200, 429}
    except Exception:
        return False


def _configure_openai(env: dict[str, str]) -> None:
    auth_method = select("Método de autenticação:", [
        "Login com conta (OAuth no navegador)",
        "Colar API key diretamente",
    ])
    using_oauth = auth_method.startswith("Login")

    if using_oauth:
        credential = _oauth_login_with_ui("openai")
        env["SOCC_AUTH_METHOD_OPENAI"] = "oauth"
    else:
        credential = ask_secret("API Key OpenAI")
        env["SOCC_AUTH_METHOD_OPENAI"] = "api_key"

    if not credential:
        _warn("Nenhuma credencial obtida para OpenAI.")
        return

    env["LLM_ENABLED"] = "true"
    url_default = "https://chatgpt.com/backend-api" if using_oauth else "https://api.openai.com/v1"
    model_default = "gpt-5-codex" if using_oauth else "gpt-4o-mini"
    url = _normalize_openai_endpoint(
        ask("URL da API OpenAI", default=url_default),
        env.get("SOCC_AUTH_METHOD_OPENAI", "api_key"),
    )
    model = ask("Modelo OpenAI", default=model_default)

    env["SOCC_OPENAI_COMPAT_URL"] = url
    env["SOCC_OPENAI_COMPAT_MODEL"] = model
    env["SOCC_OPENAI_COMPAT_API_KEY"] = credential

    if not env.get("SOCC_LLM_FALLBACK_PROVIDER"):
        env["SOCC_LLM_FALLBACK_PROVIDER"] = "openai-compatible"

    if confirm("Testar conexão?"):
        ok = _probe_spinner(
            "Validando credencial OpenAI",
            lambda: _test_openai_credential(credential, url, model=model, auth_method=env.get("SOCC_AUTH_METHOD_OPENAI", "api_key")),
        )
        if ok:
            _ok("Conexão OpenAI validada.")
        else:
            _warn("Falha na validação.")
            if using_oauth and confirm("Refazer login OAuth agora?", default=True):
                new_token = _oauth_login_with_ui("openai")
                if new_token:
                    env["SOCC_OPENAI_COMPAT_API_KEY"] = new_token
                    retried_ok = _probe_spinner(
                        "Revalidando",
                        lambda t=new_token: _test_openai_credential(t, url, model=model, auth_method="oauth"),
                    )
                    if retried_ok:
                        _ok("Conexão OK após refazer o login.")
                    else:
                        _warn("Credencial renovada, mas API ainda não respondeu.")

    _ok("OpenAI configurado.")


def _configure_manual_provider(env: dict[str, str]) -> None:
    env["LLM_ENABLED"] = "true"
    url = ask("URL do endpoint OpenAI-compatible", default="")
    if url:
        env["SOCC_OPENAI_COMPAT_URL"] = url
    api_key = ask_secret("API Key")
    if api_key:
        env["SOCC_OPENAI_COMPAT_API_KEY"] = api_key
    model = ask("Modelo", default="")
    if model:
        env["SOCC_OPENAI_COMPAT_MODEL"] = model
    if not env.get("SOCC_LLM_FALLBACK_PROVIDER"):
        env["SOCC_LLM_FALLBACK_PROVIDER"] = "openai-compatible"
    _ok("Provider manual configurado.")


def step_cloud_provider(env: dict[str, str]) -> None:
    _section_header(5, TOTAL_STEPS, "Providers de Nuvem")

    if not confirm("Configurar providers de nuvem?", default=False):
        skip("Sem provider de nuvem configurado.")
        return

    configured: list[str] = []

    while True:
        options: list[str] = []
        anthropic_done = "SOCC_AUTH_METHOD_ANTHROPIC" in env
        openai_done = "SOCC_AUTH_METHOD_OPENAI" in env

        options.append("Anthropic (Claude)" + (" [configurado]" if anthropic_done else ""))
        options.append("OpenAI (ChatGPT/Codex)" + (" [configurado]" if openai_done else ""))
        options.append("API key manual (qualquer provider)")
        options.append("Continuar >>")

        chosen = select("Adicionar provider:", options)

        if chosen.startswith("Continuar"):
            break

        if chosen.startswith("Anthropic"):
            _configure_anthropic(env)
            if "SOCC_AUTH_METHOD_ANTHROPIC" in env:
                configured.append("anthropic")
        elif chosen.startswith("OpenAI"):
            _configure_openai(env)
            if "SOCC_AUTH_METHOD_OPENAI" in env:
                configured.append("openai-compatible")
        elif chosen.startswith("API key manual"):
            _configure_manual_provider(env)
            configured.append("openai-compatible")

    # Atualiza BACKEND_PRIORITY incluindo providers de nuvem
    local_backends = [b for b in env.get("_LOCAL_BACKENDS", "").split(",") if b]
    all_backends = local_backends + [c for c in configured if c not in local_backends]
    if all_backends:
        env["SOCC_BACKEND_PRIORITY"] = ",".join(all_backends)

    # Se o primary ainda é auto/ollama mas agora tem anthropic, sugere mudar
    current_primary = env.get("SOCC_INFERENCE_BACKEND", "auto")
    if "anthropic" in configured and current_primary in ("auto", "ollama"):
        if confirm("Usar Anthropic como backend primário?", default=True):
            env["SOCC_INFERENCE_BACKEND"] = "anthropic"
    elif "openai-compatible" in configured and current_primary in ("auto", "ollama"):
        if confirm("Usar OpenAI como backend primário?", default=False):
            env["SOCC_INFERENCE_BACKEND"] = "openai-compatible"

    if configured:
        _ok(f"Providers configurados: {', '.join(configured)}")
    else:
        skip("Nenhum provider de nuvem configurado.")


def step_threat_intel(env: dict[str, str]) -> None:
    _section_header(6, TOTAL_STEPS, "Threat Intelligence")

    if not confirm("Integrar com Threat Intelligence Tool?", default=False):
        skip("Threat Intel não configurado.")
        return

    url = ask("URL da API TI", default=os.environ.get("TI_API_BASE_URL", "http://localhost:8000"))
    user = ask("Usuário TI", default="admin")
    passwd = ask_secret("Senha TI")

    env["TI_API_BASE_URL"] = url
    env["TI_API_USER"] = user
    if passwd:
        env["TI_API_PASS"] = passwd

    if confirm("Testar conexão?"):
        ok = _probe_spinner("Testando TI", lambda: _test_ti(url))
        if ok:
            _ok("Conexão OK com Threat Intel.")
        else:
            _warn(f"Não foi possível conectar em {url}.")


def _test_ti(url: str) -> bool:
    try:
        import requests
        resp = requests.get(f"{url}/api/health", timeout=5)
        return resp.status_code < 500
    except Exception:
        return False


def step_vantage(env: dict[str, str]) -> None:
    _section_header(7, TOTAL_STEPS, "Vantage (Threat Intelligence Platform)")

    _info("Plataforma de threat intelligence do time: feeds, recon, watchlists, hunting e exposure.")

    if not confirm("Você tem acesso à API do Vantage?", default=False):
        env["SOCC_VANTAGE_ENABLED"] = "false"
        skip("Vantage não configurado.")
        return

    current_url = os.environ.get("SOCC_VANTAGE_BASE_URL", "")
    url = ask("Endereço da API Vantage", default=current_url)
    if not url:
        _warn("Endereço não informado. Vantage desabilitado.")
        env["SOCC_VANTAGE_ENABLED"] = "false"
        return

    auth = select("Método de autenticação:", ["Bearer Token", "API Key"])
    if auth == "Bearer Token":
        token = ask_secret("Bearer Token")
        if token:
            env["SOCC_VANTAGE_BEARER_TOKEN"] = token
    else:
        api_key = ask_secret("API Key")
        if api_key:
            env["SOCC_VANTAGE_API_KEY"] = api_key

    env["SOCC_VANTAGE_ENABLED"] = "true"
    env["SOCC_VANTAGE_BASE_URL"] = url
    env["SOCC_VANTAGE_VERIFY_TLS"] = "true" if confirm("Verificar certificado TLS?", default=True) else "false"

    all_modules = ["dashboard", "feed", "recon", "watchlist", "hunting", "exposure", "users", "admin"]
    default_on = [True, True, True, True, True, True, False, False]
    selected = checklist("Módulos a ativar:", all_modules, defaults=default_on)
    if selected:
        env["SOCC_VANTAGE_ENABLED_MODULES"] = ",".join(selected)

    if confirm("Testar conexão?"):
        ok = _probe_spinner("Testando Vantage", lambda: _test_vantage(url, env))
        if ok:
            _ok(f"Vantage conectado. {len(selected)} módulos ativos.")
        else:
            _warn("Não foi possível conectar. Verifique URL e credenciais.")
    else:
        _ok(f"Vantage: {url} ({len(selected)} módulos)")


def _test_vantage(url: str, env: dict[str, str]) -> bool:
    try:
        import requests
        headers: dict[str, str] = {}
        if env.get("SOCC_VANTAGE_BEARER_TOKEN"):
            headers["Authorization"] = f"Bearer {env['SOCC_VANTAGE_BEARER_TOKEN']}"
        elif env.get("SOCC_VANTAGE_API_KEY"):
            headers["X-API-Key"] = env["SOCC_VANTAGE_API_KEY"]
        verify = env.get("SOCC_VANTAGE_VERIFY_TLS", "true") == "true"
        resp = requests.get(f"{url}/api/stats", headers=headers, timeout=10, verify=verify)
        return resp.status_code < 400
    except Exception:
        return False


def step_agent(env: dict[str, str]) -> None:
    _section_header(8, TOTAL_STEPS, "Agente Ativo")

    try:
        from socc.core.agent_loader import list_available_agents
        raw_agents = list_available_agents()
        agent_labels = [
            str(a.get("label") or a.get("id") or a.get("name") or "agent")
            if isinstance(a, dict) else str(a)
            for a in raw_agents
        ]
    except Exception:
        agent_labels = []

    if not agent_labels:
        agent_labels = ["soc-copilot"]
        _warn("Usando agente padrão: soc-copilot")

    if len(agent_labels) == 1:
        _ok(f"Agente: {agent_labels[0]}")
        return

    chosen = select("Agentes disponíveis:", agent_labels)
    _ok(f"Agente: {chosen}")


def step_output_dir(env: dict[str, str]) -> None:
    _section_header(9, TOTAL_STEPS, "Pasta de Saída")
    default = os.environ.get("OUTPUT_DIR", "")
    out = ask_path("Onde salvar notas e drafts gerados?", default=default)
    if out:
        out.mkdir(parents=True, exist_ok=True)
        env["OUTPUT_DIR"] = str(out)
        _ok(f"Saída: {out}")
    else:
        skip("Pasta de saída será configurada depois.")


def step_features(env: dict[str, str]) -> None:
    _section_header(10, TOTAL_STEPS, "Feature Flags")

    if not confirm("Alterar feature flags? (todas ON por padrão)", default=False):
        skip("Feature flags mantidas no padrão (todas ON).")
        return

    features = ["Analyze API", "Draft API", "Chat API", "Chat Streaming",
                "Feedback API", "Export API", "Threat Intel", "Runtime API"]
    feature_keys = [
        "SOCC_FEATURE_ANALYZE_API", "SOCC_FEATURE_DRAFT_API", "SOCC_FEATURE_CHAT_API",
        "SOCC_FEATURE_CHAT_STREAMING", "SOCC_FEATURE_FEEDBACK_API", "SOCC_FEATURE_EXPORT_API",
        "SOCC_FEATURE_THREAT_INTEL", "SOCC_FEATURE_RUNTIME_API",
    ]

    chosen = checklist("Funcionalidades ativas:", features, defaults=[True] * len(features))
    for feat, key in zip(features, feature_keys):
        env[key] = "true" if feat in chosen else "false"
    _ok(f"{len(chosen)}/{len(features)} features ativas.")


def step_security(env: dict[str, str]) -> None:
    _section_header(11, TOTAL_STEPS, "Segurança e Observabilidade")
    redact = confirm("Redação de dados sensíveis em logs?", default=True)
    audit = confirm("Auditoria de prompts?", default=False)
    env["SOCC_LOG_REDACTION_ENABLED"] = "true" if redact else "false"
    env["SOCC_PROMPT_AUDIT_ENABLED"] = "true" if audit else "false"
    _ok(f"Redação={'sim' if redact else 'não'}  Audit={'sim' if audit else 'não'}")


def _rich_summary(env: dict[str, str]) -> None:
    console = _get_console()
    if not console:
        display = {k: v for k, v in sorted(env.items()) if not k.startswith("_")}
        summary("Configuração do SOCC", display)
        return
    try:
        from rich.table import Table
        from rich.panel import Panel

        table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 2))
        table.add_column("Variável", style="cyan", no_wrap=True)
        table.add_column("Valor", style="white")

        for k, v in sorted(env.items()):
            if k.startswith("_"):
                continue
            display_v = v
            if any(s in k.lower() for s in ("key", "token", "pass", "secret")):
                display_v = v[:6] + "****" + v[-4:] if len(v) > 10 else "****"
            table.add_row(k, display_v)

        console.print()
        console.print(Panel(table, title="[bold cyan]Configuração do SOCC[/bold cyan]", border_style="cyan"))
    except Exception:
        display = {k: v for k, v in sorted(env.items()) if not k.startswith("_")}
        summary("Configuração do SOCC", display)


def step_summary_and_save(env: dict[str, str], runtime_home: Path) -> bool:
    _section_header(12, TOTAL_STEPS, "Resumo e Confirmação")
    _rich_summary(env)

    if not confirm("Salvar configuração?"):
        _warn("Configuração não salva.")
        return False

    from socc.utils.config_loader import batch_update_env
    env_path = runtime_home / ".env"
    persist = {k: v for k, v in env.items() if not k.startswith("_")}
    batch_update_env(env_path, persist)
    _ok(f"Configuração salva em {env_path}")

    if env.get("_KB_INGEST_NOW") == "true":
        _ingest_kb(env, runtime_home)

    return True


def _ingest_kb(env: dict[str, str], runtime_home: Path) -> None:
    try:
        from socc.core.knowledge_base import ensure_knowledge_base, ingest_source, register_source
        ensure_knowledge_base(runtime_home)
        source_path = env.get("_KB_SOURCE_PATH", "")
        if not source_path:
            return
        tags = [t.strip() for t in env.get("_KB_SOURCE_TAGS", "").split(",") if t.strip()]
        register_source(
            source_id="onboard-kb",
            name="Base Local (onboard)",
            kind=env.get("_KB_SOURCE_KIND", "document_set"),
            trust=env.get("_KB_SOURCE_TRUST", "internal"),
            path=source_path,
            tags=tags,
            description="Fonte registrada durante o onboard wizard.",
            home=runtime_home,
        )
        result = ingest_source(source_id="onboard-kb", home=runtime_home)
        _ok(f"KB indexada: {result.get('documents_indexed', 0)} docs, {result.get('chunks_indexed', 0)} chunks.")
    except Exception as exc:
        _warn(f"Falha na indexação: {exc}")


# ---------------------------------------------------------------------------
# Main wizard orchestrator
# ---------------------------------------------------------------------------

def run_onboard_wizard(home: Path | None = None) -> dict[str, Any]:
    if not is_interactive():
        return {"wizard": False, "reason": "non-interactive mode"}

    _banner()

    env: dict[str, str] = {}

    try:
        runtime_home = step_runtime_home(env, home)
        step_knowledge_base(env)
        step_backend(env)
        step_models(env)
        step_cloud_provider(env)
        step_threat_intel(env)
        step_vantage(env)
        step_agent(env)
        step_output_dir(env)
        step_features(env)
        step_security(env)
        saved = step_summary_and_save(env, runtime_home)
    except KeyboardInterrupt:
        console = _get_console()
        if console:
            console.print("\n\n[dim]Onboard cancelado.[/dim]")
        else:
            print("\n\nOnboard cancelado pelo usuário.")
        return {"wizard": True, "completed": False, "reason": "cancelled"}

    result: dict[str, Any] = {
        "wizard": True,
        "completed": saved,
        "runtime_home": str(runtime_home),
        "keys_configured": len([k for k in env if not k.startswith("_")]),
    }

    if saved:
        console = _get_console()
        if console:
            from rich.panel import Panel
            console.print()
            console.print(Panel(
                "[bold green]✓ SOCC configurado com sucesso![/bold green]\n\n"
                "[cyan]socc doctor[/cyan]          → Validar o ambiente\n"
                "[cyan]socc serve[/cyan]            → Iniciar a interface web\n"
                "[cyan]socc chat --interactive[/cyan] → Chat interativo\n"
                "[cyan]socc analyze --text ...[/cyan] → Analisar payload",
                title="[bold]Próximos passos[/bold]",
                border_style="green",
            ))
        else:
            print("\n--- Próximos passos ---")
            print("  socc doctor          Validar o ambiente")
            print("  socc serve           Iniciar a interface web")
            print("  socc chat --interactive  Iniciar chat interativo")

        if confirm("\nIniciar serviço agora?", default=False):
            try:
                from socc.cli.service_manager import start_service
                svc = start_service(home=runtime_home)
                if svc.get("started"):
                    _ok(f"Serviço iniciado: {svc.get('url')}")
                    result["service_started"] = True
                    result["service_url"] = svc.get("url")
            except Exception as exc:
                _warn(f"Falha ao iniciar serviço: {exc}")

        if confirm("Abrir dashboard?", default=False):
            try:
                from socc.cli.service_manager import open_dashboard
                open_dashboard(runtime_home)
            except Exception:
                pass

    return result
