"""
run.py
Ponto de entrada do SOC Copilot.
Execute: python run.py
"""
import sys
from pathlib import Path

# Garante que o pacote soc_copilot seja encontrado
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn
from soc_copilot.config import SOC_PORT

if __name__ == "__main__":
    print(f"\n  SOC Copilot MVP — iT.eam")
    print(f"  Acesse: http://localhost:{SOC_PORT}\n")
    uvicorn.run(
        "soc_copilot.main:app",
        host="127.0.0.1",
        port=SOC_PORT,
        reload=False,
        log_level="info",
    )
