"""OAuth 2.0 Authorization Code + PKCE flow for CLI login.

Supports Anthropic and OpenAI with browser-based account login.
Tokens are stored in ``~/.socc/credentials/<provider>.json``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse, parse_qs


# ---------------------------------------------------------------------------
# Provider configs — endpoints extracted from OpenClaw source
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OAuthProvider:
    name: str
    label: str
    authorize_url: str
    token_url: str
    client_id: str
    scopes: str
    callback_port: int
    callback_path: str
    redirect_uri_override: str = ""  # se preenchido, usa este ao invés do localhost
    extra_params: dict[str, str] = field(default_factory=dict)


PROVIDERS: dict[str, OAuthProvider] = {
    "anthropic": OAuthProvider(
        name="anthropic",
        label="Anthropic (Claude)",
        authorize_url="https://claude.ai/oauth/authorize",
        token_url="https://console.anthropic.com/v1/oauth/token",
        client_id="9d1c250a-e61b-44d9-88ed-5944d1962f5e",
        scopes="org:create_api_key user:profile user:inference",
        callback_port=0,       # não usado — fluxo é via console redirect
        callback_path="",
        redirect_uri_override="https://console.anthropic.com/oauth/code/callback",
    ),
    "openai": OAuthProvider(
        name="openai",
        label="OpenAI",
        authorize_url="https://auth.openai.com/oauth/authorize",
        token_url="https://auth.openai.com/oauth/token",
        client_id="app_EMoamEEZ73f0CkXaXp7hrann",
        scopes="openid profile email offline_access",
        callback_port=1455,
        callback_path="/auth/callback",
        extra_params={
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "originator": "socc",
        },
    ),
}


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _generate_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) using S256."""
    verifier_bytes = secrets.token_bytes(32)
    verifier = base64.urlsafe_b64encode(verifier_bytes).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _generate_state() -> str:
    return secrets.token_hex(16)


# ---------------------------------------------------------------------------
# Local callback HTTP server
# ---------------------------------------------------------------------------

class _CallbackHandler(BaseHTTPRequestHandler):
    """Captures the OAuth authorization code from the browser redirect."""

    auth_code: str | None = None
    state: str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "error" in params:
            _CallbackHandler.error = params["error"][0]
            self._respond(
                400,
                "<h2>Erro na autenticação</h2>"
                f"<p>{_CallbackHandler.error}</p>"
                "<p>Você pode fechar esta janela.</p>",
            )
            return

        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]

        if code:
            _CallbackHandler.auth_code = code
            _CallbackHandler.state = state
            self._respond(
                200,
                "<h2>Login realizado com sucesso!</h2>"
                "<p>Você pode fechar esta janela e voltar ao terminal.</p>",
            )
        else:
            self._respond(400, "<h2>Código de autorização não recebido.</h2>")

    def _respond(self, status: int, body: str) -> None:
        html = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>SOCC Login</title>"
            "<style>body{font-family:system-ui;max-width:480px;margin:80px auto;"
            "text-align:center;color:#333}</style></head>"
            f"<body>{body}</body></html>"
        )
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, *_args: Any) -> None:
        pass  # suppress server logs


def _wait_for_callback(
    port: int,
    callback_path: str,
    timeout: float = 120,
) -> tuple[str | None, str | None, str | None]:
    """Start local server and wait for callback.  Returns (code, state, error)."""
    _CallbackHandler.auth_code = None
    _CallbackHandler.state = None
    _CallbackHandler.error = None

    server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    server.timeout = timeout

    def _serve() -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            server.handle_request()
            if _CallbackHandler.auth_code or _CallbackHandler.error:
                break

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    thread.join(timeout=timeout + 2)

    try:
        server.server_close()
    except Exception:
        pass

    return _CallbackHandler.auth_code, _CallbackHandler.state, _CallbackHandler.error


# ---------------------------------------------------------------------------
# Token exchange
# ---------------------------------------------------------------------------

def _exchange_code(
    provider: OAuthProvider,
    code: str,
    verifier: str,
    redirect_uri: str,
) -> dict[str, Any]:
    """Exchange authorization code for tokens."""
    import requests

    # Anthropic retorna o código no formato "auth_code#state" — precisa splittar
    state: str | None = None
    auth_code = code
    if "#" in code:
        parts = code.split("#", 1)
        auth_code = parts[0]
        state = parts[1]

    # Anthropic exige JSON; outros providers usam form-encoded
    if provider.redirect_uri_override:
        payload: dict[str, Any] = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": redirect_uri,
            "client_id": provider.client_id,
            "code_verifier": verifier,
        }
        if state:
            payload["state"] = state
        resp = requests.post(
            provider.token_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
    else:
        data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": redirect_uri,
            "client_id": provider.client_id,
            "code_verifier": verifier,
        }
        resp = requests.post(
            provider.token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )

    resp.raise_for_status()
    return resp.json()


def _refresh_access_token(
    provider: OAuthProvider,
    refresh_token: str,
) -> dict[str, Any]:
    """Refresh an expired access token."""
    import requests

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": provider.client_id,
    }

    resp = requests.post(
        provider.token_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Credential storage
# ---------------------------------------------------------------------------

def _credentials_dir() -> Path:
    d = Path.home() / ".socc" / "credentials"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_credentials(provider_name: str, tokens: dict[str, Any]) -> Path:
    """Save tokens to ~/.socc/credentials/<provider>.json."""
    path = _credentials_dir() / f"{provider_name}.json"
    # Add metadata
    tokens["provider"] = provider_name
    tokens["saved_at"] = int(time.time())
    if "expires_in" in tokens and "expires_at" not in tokens:
        tokens["expires_at"] = int(time.time()) + int(tokens["expires_in"]) - 300  # 5min buffer
    path.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    # Restrict permissions
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def load_credentials(provider_name: str) -> dict[str, Any] | None:
    """Load stored tokens.  Returns None if not found."""
    path = _credentials_dir() / f"{provider_name}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def credentials_valid(provider_name: str) -> bool:
    """Check if stored credentials exist and are not expired."""
    creds = load_credentials(provider_name)
    if not creds:
        return False
    expires_at = creds.get("expires_at", 0)
    if expires_at and expires_at < time.time():
        return False
    return bool(creds.get("access_token"))


def get_access_token(provider_name: str) -> str | None:
    """Get a valid access token, refreshing if necessary."""
    creds = load_credentials(provider_name)
    if not creds:
        return None

    access = creds.get("access_token", "")
    expires_at = creds.get("expires_at", 0)

    # Token still valid
    if expires_at > time.time() and access:
        return access

    # Try refresh
    refresh = creds.get("refresh_token", "")
    if not refresh:
        return None

    provider = PROVIDERS.get(provider_name)
    if not provider:
        return None

    try:
        new_tokens = _refresh_access_token(provider, refresh)
        new_tokens["refresh_token"] = new_tokens.get("refresh_token", refresh)
        save_credentials(provider_name, new_tokens)
        return new_tokens.get("access_token")
    except Exception:
        return None


def clear_credentials(provider_name: str) -> bool:
    """Remove stored credentials."""
    path = _credentials_dir() / f"{provider_name}.json"
    if path.exists():
        path.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# Main OAuth login flow
# ---------------------------------------------------------------------------

def oauth_login(provider_name: str, force_reauth: bool = False) -> dict[str, Any]:
    """Execute the full OAuth PKCE login flow for a provider.

    Returns a dict with ``access_token``, ``refresh_token``, ``expires_at``,
    or ``error`` on failure.
    """
    provider = PROVIDERS.get(provider_name)
    if not provider:
        return {"error": f"Provider desconhecido: {provider_name}"}

    # Check for existing valid credentials unless the caller explicitly asked
    # to run the browser flow again.
    if not force_reauth and credentials_valid(provider_name):
        token = get_access_token(provider_name)
        if token:
            return {"access_token": token, "reused": True, "provider": provider_name}

    # Generate PKCE
    verifier, challenge = _generate_pkce()
    state = _generate_state()

    # Anthropic usa redirect_uri fixo pro console deles; outros usam localhost
    if provider.redirect_uri_override:
        redirect_uri = provider.redirect_uri_override
    else:
        redirect_uri = f"http://localhost:{provider.callback_port}{provider.callback_path}"

    # Build authorization URL
    params = {
        "response_type": "code",
        "client_id": provider.client_id,
        "redirect_uri": redirect_uri,
        "scope": provider.scopes,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    params.update(provider.extra_params)
    auth_url = f"{provider.authorize_url}?{urlencode(params)}"

    # Fluxo console redirect (Anthropic): state=verifier + parâmetro code=true
    if provider.redirect_uri_override:
        # Anthropic usa state=verifier e exige code=true na URL
        params["state"] = verifier
        params["code"] = "true"
        auth_url = f"{provider.authorize_url}?{urlencode(params)}"

        print(f"\n  Abrindo login {provider.label} no navegador...")
        print(f"  Faça login, autorize o acesso e copie o código exibido.")
        try:
            webbrowser.open(auth_url)
        except Exception:
            print(f"  Não foi possível abrir automaticamente. Acesse:")
            print(f"  {auth_url}\n")
        code = input("  Cole o código de autorização aqui: ").strip()
        if not code:
            return {"error": "Nenhum código informado."}
        cb_state = None  # fluxo console não devolve state
    else:
        print(f"\n  Abrindo login {provider.label} no navegador...")
        print(f"  Faça login com sua conta e autorize o acesso.")
        print(f"  Aguardando retorno... (timeout: 2 minutos)\n")
        try:
            webbrowser.open(auth_url)
        except Exception:
            print(f"  Não foi possível abrir o navegador automaticamente.")
            print(f"  Acesse manualmente: {auth_url}\n")
        code, cb_state, error = _wait_for_callback(
            provider.callback_port,
            provider.callback_path,
            timeout=120,
        )
        if error:
            return {"error": f"Erro OAuth: {error}"}
        if not code:
            return {"error": "Timeout — nenhum código de autorização recebido."}

    # Verify state (apenas quando disponível)
    if cb_state and cb_state != state:
        return {"error": "State mismatch — possível ataque CSRF."}

    # Exchange code for tokens
    try:
        tokens = _exchange_code(provider, code, verifier, redirect_uri)
    except Exception as exc:
        return {"error": f"Falha no token exchange: {exc}"}

    # Save credentials
    save_credentials(provider_name, tokens)

    return {
        "access_token": tokens.get("access_token", ""),
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_in": tokens.get("expires_in", 0),
        "provider": provider_name,
    }


def test_oauth_token(provider_name: str, access_token: str) -> bool:
    """Test if an OAuth token is valid by calling the provider API."""
    import requests

    if provider_name == "anthropic":
        try:
            resp = requests.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "anthropic-version": "2023-06-01",
                    "anthropic-beta": "oauth-2025-04-20",
                },
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    if provider_name == "openai":
        try:
            resp = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    return False
