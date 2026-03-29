#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOCC_HOME="${SOCC_HOME:-$HOME/.socc}"
PYTHON_BIN="${PYTHON_BIN:-}"
LOCAL_BIN_DIR="${LOCAL_BIN_DIR:-$HOME/.local/bin}"
INSTALL_MODE="editable"
SKIP_DEPS="false"
FORCE_BOOTSTRAP="false"
RUN_PROBE="false"

usage() {
  cat <<EOF
SOCC install.sh

Instala o runtime local do SOCC em estilo próximo ao OpenClaw:
- venv local em ~/.socc/venv
- launcher em ~/.socc/bin/socc
- bootstrap automático do runtime

Uso:
  ./install.sh [--home PATH] [--python PATH] [--standard] [--skip-deps] [--force] [--probe]

Opções:
  --home PATH     diretório do runtime local (padrão: ~/.socc)
  --python PATH   interpretador Python a usar
  --standard      usa pip install . em vez de pip install -e .
  --skip-deps     instala o pacote com --no-deps
  --force         reexecuta onboarding com --force
  --probe         executa onboard com probe do backend configurado
  --help          mostra esta ajuda
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --home)
      SOCC_HOME="$2"
      shift 2
      ;;
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    --standard)
      INSTALL_MODE="standard"
      shift
      ;;
    --skip-deps)
      SKIP_DEPS="true"
      shift
      ;;
    --force)
      FORCE_BOOTSTRAP="true"
      shift
      ;;
    --probe)
      RUN_PROBE="true"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Argumento desconhecido: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    echo "Python não encontrado. Defina --python /caminho/python." >&2
    exit 1
  fi
fi

mkdir -p "$SOCC_HOME"

BOOTSTRAP_FORCE_PY="False"
if [[ "$FORCE_BOOTSTRAP" == "true" ]]; then
  BOOTSTRAP_FORCE_PY="True"
fi

"$PYTHON_BIN" - <<EOF
from pathlib import Path
import sys
sys.path.insert(0, "$ROOT_DIR")
from socc.cli.installer import bootstrap_runtime
bootstrap_runtime(Path("$SOCC_HOME"), force=$BOOTSTRAP_FORCE_PY)
EOF

if [[ ! -d "$SOCC_HOME/venv" ]]; then
  "$PYTHON_BIN" -m venv "$SOCC_HOME/venv"
fi

VENV_PY="$SOCC_HOME/venv/bin/python"
VENV_PIP="$SOCC_HOME/venv/bin/pip"
PIP_COMMON_ARGS=(--disable-pip-version-check --retries 0 --timeout 3)
PYTHON_HEALTHCHECK='import socc.cli.main; import requests'

if ! "$VENV_PY" -m pip install "${PIP_COMMON_ARGS[@]}" --upgrade pip setuptools wheel; then
  echo "Aviso: falha ao atualizar pip/setuptools/wheel. Seguindo com o que já estiver disponível." >&2
fi

PIP_ARGS=()
if [[ "$SKIP_DEPS" == "true" ]]; then
  PIP_ARGS+=(--no-deps)
fi
PIP_ARGS+=(--no-build-isolation)

INSTALL_OK="false"
if [[ "$INSTALL_MODE" == "editable" ]]; then
  if "$VENV_PIP" install "${PIP_COMMON_ARGS[@]}" "${PIP_ARGS[@]}" -e "$ROOT_DIR"; then
    INSTALL_OK="true"
  elif [[ "$SKIP_DEPS" != "true" ]] && "$VENV_PIP" install "${PIP_COMMON_ARGS[@]}" --no-deps --no-build-isolation -e "$ROOT_DIR"; then
    INSTALL_OK="true"
  fi
else
  if "$VENV_PIP" install "${PIP_COMMON_ARGS[@]}" "${PIP_ARGS[@]}" "$ROOT_DIR"; then
    INSTALL_OK="true"
  elif [[ "$SKIP_DEPS" != "true" ]] && "$VENV_PIP" install "${PIP_COMMON_ARGS[@]}" --no-deps --no-build-isolation "$ROOT_DIR"; then
    INSTALL_OK="true"
  fi
fi

# Garantir InquirerPy para CLI interativa (setas, toggle, autocomplete)
"$VENV_PIP" install "${PIP_COMMON_ARGS[@]}" "InquirerPy>=0.3.4" 2>/dev/null || \
  echo "Aviso: InquirerPy não instalado. CLI interativa usará modo texto simples." >&2

mkdir -p "$SOCC_HOME/bin"
cat > "$SOCC_HOME/bin/socc" <<EOF
#!/usr/bin/env bash
set -euo pipefail
SOCC_HOME="\${SOCC_HOME:-$SOCC_HOME}"
SOCC_PROJECT_ROOT="\${SOCC_PROJECT_ROOT:-$ROOT_DIR}"
VENV_PY_DEFAULT="$VENV_PY"
FALLBACK_PY_DEFAULT="$PYTHON_BIN"
if [[ -n "\${SOCC_PYTHON:-}" ]]; then
  PYTHON_TO_USE="\$SOCC_PYTHON"
elif "\$VENV_PY_DEFAULT" -c "$PYTHON_HEALTHCHECK" >/dev/null 2>&1; then
  PYTHON_TO_USE="\$VENV_PY_DEFAULT"
else
  PYTHON_TO_USE="\$FALLBACK_PY_DEFAULT"
fi
export PYTHONPATH="\$SOCC_PROJECT_ROOT\${PYTHONPATH:+:\$PYTHONPATH}"
exec "\$PYTHON_TO_USE" -m socc.cli.main "\$@"
EOF
chmod +x "$SOCC_HOME/bin/socc"

PATH_SHIM="$LOCAL_BIN_DIR/socc"
PATH_SHIM_OK="true"
if ! mkdir -p "$LOCAL_BIN_DIR" 2>/dev/null; then
  PATH_SHIM_OK="false"
elif ! cat > "$PATH_SHIM" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "$SOCC_HOME/bin/socc" "\$@"
EOF
then
  PATH_SHIM_OK="false"
else
  chmod +x "$PATH_SHIM" || PATH_SHIM_OK="false"
fi
if [[ "$PATH_SHIM_OK" != "true" ]]; then
  echo "Aviso: não foi possível criar o shim em $LOCAL_BIN_DIR. Use $SOCC_HOME/bin/socc diretamente." >&2
fi

ONBOARD_ARGS=(onboard --home "$SOCC_HOME")
if [[ "$FORCE_BOOTSTRAP" == "true" ]]; then
  ONBOARD_ARGS+=(--force)
fi
if [[ "$RUN_PROBE" == "true" ]]; then
  ONBOARD_ARGS+=(--probe)
fi
if [[ -n "${SOCC_PYTHON:-}" ]]; then
  ONBOARD_PY="$SOCC_PYTHON"
elif "$VENV_PY" -c "$PYTHON_HEALTHCHECK" >/dev/null 2>&1; then
  ONBOARD_PY="$VENV_PY"
else
  ONBOARD_PY="$PYTHON_BIN"
fi
ONBOARD_OK="true"
if ! SOCC_HOME="$SOCC_HOME" SOCC_PROJECT_ROOT="$ROOT_DIR" PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" "$ONBOARD_PY" -m socc.cli.main "${ONBOARD_ARGS[@]}"; then
  ONBOARD_OK="false"
  echo "Aviso: onboarding automático falhou. O runtime e o launcher foram criados, mas pode haver dependências faltando." >&2
fi

cat <<EOF

SOCC instalado com sucesso.

Runtime:  $SOCC_HOME
Launcher: $SOCC_HOME/bin/socc
PATH shim: $PATH_SHIM
Install mode: $INSTALL_MODE
Package install ok: $INSTALL_OK
Onboard ok: $ONBOARD_OK
PATH shim ok: $PATH_SHIM_OK

Próximos passos:
  1. Se o shim existir, garanta no PATH: export PATH="$LOCAL_BIN_DIR:\$PATH"
  2. Revise $SOCC_HOME/.env
  3. Confira o checkout visível em: $SOCC_HOME/project
  4. Rode: $SOCC_HOME/bin/socc doctor --probe
  5. Rode: $SOCC_HOME/bin/socc serve
EOF
