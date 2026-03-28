import os
from pathlib import Path
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - ambiente mínimo sem dependências
    def load_dotenv(*_args, **_kwargs):
        return False

try:
    from socc.utils.config_loader import load_environment
except ImportError:  # pragma: no cover - fallback para bootstraps mínimos
    load_environment = None

# Prioriza ~/.socc/.env quando existir, mantendo compatibilidade com .env do repositório.
if callable(load_environment):
    load_environment()
else:
    _env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(_env_path)

THREAT_CHECK_SCRIPT = os.getenv(
    "THREAT_CHECK_SCRIPT",
    r"C:\Users\Nilson.Miranda\Threat-Intelligence-Tool\backend\threat_check.py",
)
TI_API_BASE_URL = os.getenv("TI_API_BASE_URL", "http://localhost:8000")
TI_API_USER = os.getenv("TI_API_USER", "")
TI_API_PASS = os.getenv("TI_API_PASS", "")  # obrigatório via .env — sem default
THREAT_INTEL_API_KEY = os.getenv("THREAT_INTEL_API_KEY", "")

ALERTAS_ROOT = Path(
    os.getenv(
        "ALERTAS_ROOT",
        r"C:\Users\Nilson.Miranda\OneDrive - iT.eam\Documentos\Alertas",
    )
)
OUTPUT_DIR = Path(
    os.getenv(
        "OUTPUT_DIR",
        r"C:\Users\Nilson.Miranda\OneDrive - iT.eam\Documentos\Alertas\Notas_Geradas",
    )
)
BATCH_SCRIPT = os.getenv(
    "BATCH_SCRIPT",
    str(ALERTAS_ROOT / "batch.py"),
)
SOC_PORT = int(os.getenv("SOC_PORT", "8080"))
MAX_TI_IOCS = int(os.getenv("MAX_TI_IOCS", "5"))

# ---------------------------------------------------------------------------
# LLM — opcional; LLM_ENABLED=false mantém modo determinístico puro
# LLM_PROVIDER: "anthropic" (nuvem) ou "ollama" (local)
# ---------------------------------------------------------------------------
LLM_ENABLED = os.getenv("LLM_ENABLED", "false").lower() in ("true", "1", "yes")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")   # "anthropic" | "ollama"
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))

# Anthropic (nuvem)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")

# Ollama (local)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")

# Caminhos derivados
AGENT_MD = ALERTAS_ROOT / ".agents" / "rules" / "AGENT.md"
TOOLS_MD = ALERTAS_ROOT / ".agents" / "rules" / "TOOLS.md"
SOP_MD = ALERTAS_ROOT / ".agents" / "workflows" / "SOP.md"
MODELOS_DIR = ALERTAS_ROOT / "Modelos"
INVENTARIO_MD = ALERTAS_ROOT / "Automacao" / "SOC_Copilot_Regras_Inventario.md"
DB_PATH = Path(__file__).parent / "soc_copilot.db"
