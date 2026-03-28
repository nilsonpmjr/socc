"""Interactive onboarding wizard for ``socc onboard``.

Guides the user through 12 configuration steps, collecting settings and
persisting them in ``~/.socc/.env`` via :func:`batch_update_env`.
"""

from __future__ import annotations

import os
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

TOTAL_STEPS = 12


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _probe_backend_quiet(endpoint: str, backend: str) -> bool:
    """Return True if *endpoint* responds to a simple HTTP GET."""
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


def _test_anthropic_key(api_key: str) -> bool:
    try:
        import requests
        resp = requests.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=5,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _detect_gpu() -> str | None:
    """Return GPU description or None."""
    if os.environ.get("CUDA_VISIBLE_DEVICES") is not None:
        return "CUDA (via CUDA_VISIBLE_DEVICES)"
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")[0]
    except Exception:
        pass
    return None


def _scan_candidate_kb_paths() -> list[str]:
    """Return paths that look like candidate knowledge bases."""
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
    step(1, TOTAL_STEPS, "Runtime Home")
    default = str(current_home or "~/.socc")
    exists = Path(default).expanduser().exists()
    if exists:
        success(f"Runtime existente detectado em {Path(default).expanduser()}")
        if confirm("Reaproveitar runtime existente?"):
            return Path(default).expanduser()
    chosen = ask_path("Onde instalar o runtime do SOCC?", default=default) or Path(default).expanduser()
    return chosen


def step_knowledge_base(env: dict[str, str]) -> None:
    step(2, TOTAL_STEPS, "Base Local de Conhecimento")
    if not confirm("Deseja apontar uma pasta de conhecimento local (SOPs, playbooks, regras)?", default=False):
        skip("Knowledge base será configurada depois.")
        return
    candidates = _scan_candidate_kb_paths()
    default_path = candidates[0] if candidates else ""
    if candidates:
        print(f"  Candidatos detectados: {', '.join(candidates)}")
    kb_path = ask_path("Caminho da pasta de conhecimento", default=default_path, must_exist=True)
    if not kb_path:
        skip("Nenhum caminho informado.")
        return

    file_count = _count_indexable_files(kb_path)
    print(f"  {file_count} arquivos indexáveis encontrados.")

    kind_options = ["document_set", "case_notes"]
    kind = select("Tipo de fonte:", kind_options)

    trust_options = ["internal", "curated_external"]
    trust = select("Nível de confiança:", trust_options)

    tags = ask("Tags (separadas por vírgula)", default="sop,playbook")

    env["ALERTAS_ROOT"] = str(kb_path)
    env["_KB_SOURCE_PATH"] = str(kb_path)
    env["_KB_SOURCE_KIND"] = kind
    env["_KB_SOURCE_TRUST"] = trust
    env["_KB_SOURCE_TAGS"] = tags

    if file_count > 0 and confirm("Indexar agora?"):
        env["_KB_INGEST_NOW"] = "true"
    success(f"Knowledge base: {kb_path} ({file_count} arquivos)")


def step_backend(env: dict[str, str]) -> None:
    step(3, TOTAL_STEPS, "Backend de Inferência")

    backends_to_probe = {
        "ollama": os.environ.get("OLLAMA_URL", "http://localhost:11434"),
        "lmstudio": os.environ.get("SOCC_LMSTUDIO_URL", "http://127.0.0.1:1234/v1"),
        "vllm": os.environ.get("SOCC_VLLM_URL", "http://127.0.0.1:8000/v1"),
    }
    detected: list[str] = []
    for name, url in backends_to_probe.items():
        reachable = _probe_backend_quiet(url, name)
        status = "detectado" if reachable else "não encontrado"
        mark = "OK" if reachable else "--"
        print(f"  {mark} {name} em {url} ({status})")
        if reachable:
            detected.append(name)

    gpu = _detect_gpu()
    if gpu:
        success(f"GPU detectada: {gpu}")
    else:
        warning("Nenhuma GPU detectada. Device será configurado como 'cpu'.")

    all_backends = ["ollama", "lmstudio", "vllm", "openai-compatible", "anthropic", "auto"]
    default_idx = 0
    if detected:
        default_idx = all_backends.index(detected[0]) if detected[0] in all_backends else 0
    chosen = select("Qual backend de inferência usar?", all_backends, default=default_idx)

    env["SOCC_INFERENCE_BACKEND"] = chosen
    env["SOCC_INFERENCE_DEVICE"] = "gpu" if gpu else "cpu"

    if chosen == "ollama":
        url = ask("URL do Ollama", default=backends_to_probe["ollama"])
        env["OLLAMA_URL"] = url
    elif chosen == "lmstudio":
        url = ask("URL do LM Studio", default=backends_to_probe["lmstudio"])
        env["SOCC_LMSTUDIO_URL"] = url
    elif chosen == "vllm":
        url = ask("URL do vLLM", default=backends_to_probe["vllm"])
        env["SOCC_VLLM_URL"] = url
    elif chosen == "openai-compatible":
        url = ask("URL do endpoint OpenAI-compatible", default="")
        if url:
            env["SOCC_OPENAI_COMPAT_URL"] = url
        model = ask("Modelo padrão", default="")
        if model:
            env["SOCC_OPENAI_COMPAT_MODEL"] = model

    success(f"Backend: {chosen} (device: {'gpu' if gpu else 'cpu'})")


def step_models(env: dict[str, str]) -> None:
    step(4, TOTAL_STEPS, "Seleção de Modelos")

    backend = env.get("SOCC_INFERENCE_BACKEND", "ollama")
    models: list[str] = []

    if backend in ("ollama", "auto"):
        endpoint = env.get("OLLAMA_URL", os.environ.get("OLLAMA_URL", "http://localhost:11434"))
        models = _list_ollama_models(endpoint)
        if models:
            print(f"  Modelos instalados no Ollama:")
            for m in models:
                print(f"    - {m}")
        else:
            warning("Nenhum modelo encontrado no Ollama. Configure manualmente.")

    if models:
        fast = select("Perfil Fast (rápido, triagem):", models, default=min(len(models) - 1, 0))
        balanced_default = 0
        for i, m in enumerate(models):
            if "9b" in m or "7b" in m or "8b" in m:
                balanced_default = i
                break
        balanced = select("Perfil Balanced (equilibrado, análise):", models, default=balanced_default)
        deep = select("Perfil Deep (profundo, drafts complexos):", models, default=balanced_default)
        env["SOCC_OLLAMA_FAST_MODEL"] = fast
        env["SOCC_OLLAMA_BALANCED_MODEL"] = balanced
        env["SOCC_OLLAMA_DEEP_MODEL"] = deep
        env["OLLAMA_MODEL"] = balanced
    else:
        fast = ask("Modelo Fast", default="llama3.2:3b")
        balanced = ask("Modelo Balanced", default="qwen3.5:9b")
        deep = ask("Modelo Deep", default="qwen3.5:9b")
        env["SOCC_OLLAMA_FAST_MODEL"] = fast
        env["SOCC_OLLAMA_BALANCED_MODEL"] = balanced
        env["SOCC_OLLAMA_DEEP_MODEL"] = deep
        env["OLLAMA_MODEL"] = balanced

    success(f"Fast={fast}  Balanced={balanced}  Deep={deep}")


def _anthropic_oauth_login() -> str | None:
    """Open browser for Anthropic Console login and retrieve API key.

    Returns the API key if the user provides it after logging in, or None.
    """
    import webbrowser

    print("\n  Abrindo o Anthropic Console no navegador...")
    print("  1. Faça login em https://console.anthropic.com/")
    print("  2. Vá em Settings > API Keys")
    print("  3. Crie ou copie uma API key")
    print()
    try:
        webbrowser.open("https://console.anthropic.com/settings/keys")
    except Exception:
        warning("Não foi possível abrir o navegador. Acesse manualmente.")
    return ask_secret("Cole a API Key Anthropic aqui") or None


def _openai_oauth_login() -> str | None:
    """Open browser for OpenAI Platform login and retrieve API key.

    Returns the API key if the user provides it after logging in, or None.
    """
    import webbrowser

    print("\n  Abrindo o OpenAI Platform no navegador...")
    print("  1. Faça login em https://platform.openai.com/")
    print("  2. Vá em API Keys")
    print("  3. Crie ou copie uma API key")
    print()
    try:
        webbrowser.open("https://platform.openai.com/api-keys")
    except Exception:
        warning("Não foi possível abrir o navegador. Acesse manualmente.")
    return ask_secret("Cole a API Key OpenAI aqui") or None


def _test_openai_key(api_key: str, url: str = "https://api.openai.com/v1") -> bool:
    try:
        import requests
        resp = requests.get(
            f"{url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5,
        )
        return resp.status_code == 200
    except Exception:
        return False


def step_cloud_provider(env: dict[str, str]) -> None:
    step(5, TOTAL_STEPS, "Provider de Nuvem (fallback)")

    if not confirm("Configurar um provider de nuvem como fallback?", default=False):
        skip("Sem fallback de nuvem configurado.")
        return

    providers = [
        "Anthropic (login via navegador)",
        "OpenAI (login via navegador)",
        "API key manual (qualquer provider)",
        "Pular",
    ]
    chosen = select("Provider:", providers)

    if chosen == "Pular":
        skip("Provider de nuvem ignorado.")
        return

    if chosen.startswith("Anthropic"):
        auth_method = select("Método de autenticação:", [
            "Login no navegador (abre console.anthropic.com)",
            "Colar API key diretamente",
        ])
        if auth_method.startswith("Login"):
            api_key = _anthropic_oauth_login()
        else:
            api_key = ask_secret("API Key Anthropic")

        if not api_key:
            warning("Nenhuma API key informada.")
            return
        env["ANTHROPIC_API_KEY"] = api_key
        env["SOCC_LLM_FALLBACK_PROVIDER"] = "anthropic"
        model = ask("Modelo Anthropic", default="claude-haiku-4-5-20251001")
        env["LLM_MODEL"] = model
        if confirm("Testar conexão?"):
            if _test_anthropic_key(api_key):
                success("Conexão OK — provider Anthropic validado.")
            else:
                warning("Falha na validação. Verifique a API key.")
        success("Fallback: anthropic")

    elif chosen.startswith("OpenAI"):
        auth_method = select("Método de autenticação:", [
            "Login no navegador (abre platform.openai.com)",
            "Colar API key diretamente",
        ])
        if auth_method.startswith("Login"):
            api_key = _openai_oauth_login()
        else:
            api_key = ask_secret("API Key OpenAI")

        if not api_key:
            warning("Nenhuma API key informada.")
            return

        url = ask("URL da API OpenAI", default="https://api.openai.com/v1")
        env["SOCC_OPENAI_COMPAT_URL"] = url
        env["SOCC_OPENAI_COMPAT_MODEL"] = ask("Modelo", default="gpt-4o-mini")
        env["SOCC_LLM_FALLBACK_PROVIDER"] = "openai-compatible"
        # Armazenar key como bearer (OpenAI-compatible usa Authorization header)
        env["SOCC_OPENAI_COMPAT_API_KEY"] = api_key

        if confirm("Testar conexão?"):
            if _test_openai_key(api_key, url):
                success("Conexão OK — provider OpenAI validado.")
            else:
                warning("Falha na validação. Verifique a API key.")
        success("Fallback: openai")

    else:
        # API key manual genérica
        url = ask("URL do endpoint OpenAI-compatible", default="")
        if url:
            env["SOCC_OPENAI_COMPAT_URL"] = url
        api_key = ask_secret("API Key")
        if api_key:
            env["SOCC_OPENAI_COMPAT_API_KEY"] = api_key
        model = ask("Modelo", default="")
        if model:
            env["SOCC_OPENAI_COMPAT_MODEL"] = model
        env["SOCC_LLM_FALLBACK_PROVIDER"] = "openai-compatible"
        success("Fallback: openai-compatible")


def step_threat_intel(env: dict[str, str]) -> None:
    step(6, TOTAL_STEPS, "Threat Intelligence")

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
        try:
            import requests
            resp = requests.get(f"{url}/api/health", timeout=5)
            if resp.status_code < 500:
                success("Conexão OK com Threat Intel.")
            else:
                warning(f"Resposta HTTP {resp.status_code}.")
        except Exception as exc:
            warning(f"Falha na conexão: {exc}")


def step_vantage(env: dict[str, str]) -> None:
    step(7, TOTAL_STEPS, "Vantage (Threat Intelligence Platform)")

    print("  O Vantage é a plataforma de threat intelligence do seu time.")
    print("  Ele fornece feeds, recon, watchlists, hunting e exposure.")
    print("  Se você tem acesso à API, configure aqui para enriquecer análises.\n")

    if not confirm("Você tem acesso à API do Vantage?", default=False):
        env["SOCC_VANTAGE_ENABLED"] = "false"
        skip("Vantage não configurado.")
        return

    current_url = os.environ.get("SOCC_VANTAGE_BASE_URL", "")
    url = ask("Endereço da sua API Vantage (ex: https://vantage.seutime.com)", default=current_url)
    if not url:
        warning("Endereço não informado. Vantage desabilitado.")
        env["SOCC_VANTAGE_ENABLED"] = "false"
        return

    auth_options = ["Bearer Token", "API Key"]
    auth = select("Como você se autentica na API?", auth_options)

    if auth == "Bearer Token":
        token = ask_secret("Bearer Token do Vantage")
        if token:
            env["SOCC_VANTAGE_BEARER_TOKEN"] = token
    else:
        api_key = ask_secret("API Key do Vantage")
        if api_key:
            env["SOCC_VANTAGE_API_KEY"] = api_key

    env["SOCC_VANTAGE_ENABLED"] = "true"
    env["SOCC_VANTAGE_BASE_URL"] = url

    verify_tls = confirm("Verificar certificado TLS?", default=True)
    env["SOCC_VANTAGE_VERIFY_TLS"] = "true" if verify_tls else "false"

    # Módulos disponíveis
    all_modules = ["dashboard", "feed", "recon", "watchlist", "hunting", "exposure", "users", "admin"]
    default_on = [True, True, True, True, True, True, False, False]
    selected = checklist("Módulos do Vantage a ativar:", all_modules, defaults=default_on)
    if selected:
        env["SOCC_VANTAGE_ENABLED_MODULES"] = ",".join(selected)

    if confirm("Testar conexão com o Vantage?"):
        try:
            import requests
            headers: dict[str, str] = {}
            if env.get("SOCC_VANTAGE_BEARER_TOKEN"):
                headers["Authorization"] = f"Bearer {env['SOCC_VANTAGE_BEARER_TOKEN']}"
            elif env.get("SOCC_VANTAGE_API_KEY"):
                headers["X-API-Key"] = env["SOCC_VANTAGE_API_KEY"]
            resp = requests.get(
                f"{url}/api/stats",
                headers=headers,
                timeout=10,
                verify=verify_tls,
            )
            if resp.status_code < 400:
                success(f"Conexão OK com Vantage ({resp.status_code}). {len(selected)} módulos ativos.")
            else:
                warning(f"Resposta HTTP {resp.status_code}. Verifique credenciais e URL.")
        except Exception as exc:
            warning(f"Falha na conexão: {exc}")
    else:
        success(f"Vantage: {url} ({len(selected)} módulos)")


def step_agent(env: dict[str, str]) -> None:
    step(8, TOTAL_STEPS, "Agente Ativo")

    try:
        from socc.core.agent_loader import list_available_agents
        raw_agents = list_available_agents()
        # Extract display labels from dicts
        agent_labels: list[str] = []
        for a in raw_agents:
            if isinstance(a, dict):
                label = str(a.get("label") or a.get("id") or a.get("name") or "agent")
                agent_labels.append(label)
            else:
                agent_labels.append(str(a))
    except Exception:
        raw_agents = []
        agent_labels = []

    if not agent_labels:
        agent_labels = ["soc-copilot"]
        warning("Usando agente padrão: soc-copilot")

    if len(agent_labels) == 1:
        success(f"Agente: {agent_labels[0]}")
        return

    chosen = select("Agentes disponíveis:", agent_labels)
    success(f"Agente: {chosen}")


def step_output_dir(env: dict[str, str]) -> None:
    step(9, TOTAL_STEPS, "Pasta de Saída")

    default = os.environ.get("OUTPUT_DIR", "")
    out = ask_path("Onde salvar notas e drafts gerados?", default=default)
    if out:
        out.mkdir(parents=True, exist_ok=True)
        env["OUTPUT_DIR"] = str(out)
        success(f"Saída: {out}")
    else:
        skip("Pasta de saída será configurada depois.")


def step_features(env: dict[str, str]) -> None:
    step(10, TOTAL_STEPS, "Feature Flags")

    features = [
        "Analyze API",
        "Draft API",
        "Chat API",
        "Chat Streaming",
        "Feedback API",
        "Export API",
        "Threat Intel",
        "Runtime API",
    ]
    feature_keys = [
        "SOCC_FEATURE_ANALYZE_API",
        "SOCC_FEATURE_DRAFT_API",
        "SOCC_FEATURE_CHAT_API",
        "SOCC_FEATURE_CHAT_STREAMING",
        "SOCC_FEATURE_FEEDBACK_API",
        "SOCC_FEATURE_EXPORT_API",
        "SOCC_FEATURE_THREAT_INTEL",
        "SOCC_FEATURE_RUNTIME_API",
    ]
    defaults = [True] * len(features)

    if not confirm("Alterar feature flags? (todas ON por padrão)", default=False):
        skip("Feature flags mantidas no padrão (todas ON).")
        return

    chosen = checklist("Funcionalidades ativas:", features, defaults=defaults)
    for feat, key in zip(features, feature_keys):
        env[key] = "true" if feat in chosen else "false"
    success(f"{len(chosen)}/{len(features)} features ativas.")


def step_security(env: dict[str, str]) -> None:
    step(11, TOTAL_STEPS, "Segurança e Observabilidade")

    redact = confirm("Redação de dados sensíveis em logs?", default=True)
    env["SOCC_LOG_REDACTION_ENABLED"] = "true" if redact else "false"

    audit = confirm("Auditoria de prompts?", default=False)
    env["SOCC_PROMPT_AUDIT_ENABLED"] = "true" if audit else "false"

    success(f"Redação={'sim' if redact else 'não'}  Audit={'sim' if audit else 'não'}")


def step_summary_and_save(env: dict[str, str], runtime_home: Path) -> bool:
    step(12, TOTAL_STEPS, "Resumo e Confirmação")

    # Build display items from env, excluding internal keys
    display: dict[str, str] = {}
    for key, value in sorted(env.items()):
        if key.startswith("_"):
            continue
        display[key] = value

    summary("Configuração do SOCC", display)

    if not confirm("Salvar configuração?"):
        warning("Configuração não salva.")
        return False

    # Persist to .env
    from socc.utils.config_loader import batch_update_env
    env_path = runtime_home / ".env"
    persist = {k: v for k, v in env.items() if not k.startswith("_")}
    batch_update_env(env_path, persist)
    success(f"Configuração salva em {env_path}")

    # Knowledge base ingestion if requested
    if env.get("_KB_INGEST_NOW") == "true":
        _ingest_kb(env, runtime_home)

    return True


def _ingest_kb(env: dict[str, str], runtime_home: Path) -> None:
    """Register and ingest the knowledge base source configured in the wizard."""
    try:
        from socc.core.knowledge_base import ensure_knowledge_base, ingest_source, register_source

        ensure_knowledge_base(runtime_home)
        source_path = env.get("_KB_SOURCE_PATH", "")
        if not source_path:
            return
        tags_raw = env.get("_KB_SOURCE_TAGS", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
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
        docs = result.get("documents_indexed", 0)
        chunks = result.get("chunks_indexed", 0)
        success(f"KB indexada: {docs} documentos, {chunks} chunks.")
    except Exception as exc:
        warning(f"Falha na indexação: {exc}")


# ---------------------------------------------------------------------------
# Main wizard orchestrator
# ---------------------------------------------------------------------------

def run_onboard_wizard(home: Path | None = None) -> dict[str, Any]:
    """Execute the full 12-step onboard wizard.  Returns a result payload."""
    if not is_interactive():
        return {"wizard": False, "reason": "non-interactive mode"}

    print("\n" + "=" * 50)
    print("  SOCC — Wizard de Onboarding")
    print("=" * 50)
    print("Responda as perguntas para configurar o runtime.")
    print("Pressione Ctrl+C a qualquer momento para cancelar.\n")

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
        print("\n\nOnboard cancelado pelo usuário.")
        return {"wizard": True, "completed": False, "reason": "cancelled"}

    result: dict[str, Any] = {
        "wizard": True,
        "completed": saved,
        "runtime_home": str(runtime_home),
        "keys_configured": len([k for k in env if not k.startswith("_")]),
    }

    if saved:
        print("\n--- Próximos passos ---")
        print("  socc doctor --probe     Validar o ambiente")
        print("  socc serve              Iniciar a interface web")
        print("  socc dashboard --open   Abrir o dashboard no navegador")
        print("  socc chat --interactive Iniciar chat interativo")

        if confirm("\nIniciar serviço agora?", default=False):
            try:
                from socc.cli.service_manager import start_service
                svc = start_service(home=runtime_home)
                if svc.get("started"):
                    success(f"Serviço iniciado: {svc.get('url')}")
                    result["service_started"] = True
                    result["service_url"] = svc.get("url")
            except Exception as exc:
                warning(f"Falha ao iniciar serviço: {exc}")

        if confirm("Abrir dashboard?", default=False):
            try:
                from socc.cli.service_manager import open_dashboard
                open_dashboard(runtime_home)
            except Exception:
                pass

    return result
