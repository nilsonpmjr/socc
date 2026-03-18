import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega .env da pasta pai (Automacao/)
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

# Caminhos derivados
AGENT_MD = ALERTAS_ROOT / ".agents" / "rules" / "AGENT.md"
TOOLS_MD = ALERTAS_ROOT / ".agents" / "rules" / "TOOLS.md"
SOP_MD = ALERTAS_ROOT / ".agents" / "workflows" / "SOP.md"
MODELOS_DIR = ALERTAS_ROOT / "Modelos"
INVENTARIO_MD = ALERTAS_ROOT / "Automacao" / "SOC_Copilot_Regras_Inventario.md"
DB_PATH = Path(__file__).parent / "soc_copilot.db"
