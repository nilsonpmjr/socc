"""
mcp_server.py — Servidor MCP do SOCC

Expõe as ferramentas do SOC Copilot como recursos MCP para que qualquer
cliente compatível (Claude Desktop, Cursor, etc.) possa:

  - ler as regras do agente (.agents/)
  - consultar modelos existentes (Modelos/)
  - executar análise determinística
  - acessar histórico de casos (SQLite)
  - enriquecer IOCs via VANTAGE

Uso:
  python mcp_server.py

Configuração no Claude Desktop (claude_desktop_config.json):
  {
    "mcpServers": {
      "socc": {
        "command": "python",
        "args": ["C:/Users/Nilson.Miranda/OneDrive - iT.eam/Documentos/Alertas/socc/mcp_server.py"]
      }
    }
  }
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Garante que o pacote soc_copilot seja encontrado
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from fastmcp import FastMCP
from soc_copilot import config as cfg

mcp = FastMCP(
    name="SOCC — SOC Copilot",
    instructions=(
        "Ferramentas do SOC Copilot (iT.eam). Use estas ferramentas para analisar "
        "offenses de segurança, consultar regras do agente, acessar modelos de alerta "
        "e enriquecer indicadores de comprometimento. Sempre siga as regras do "
        "AGENT.md ao redigir texto de alertas."
    ),
)

# ---------------------------------------------------------------------------
# Resources — arquivos do .agents/ como contexto de leitura
# ---------------------------------------------------------------------------

@mcp.resource("agent://rules/agent-md")
def get_agent_rules() -> str:
    """Regras obrigatórias do agente SOC (AGENT.md) — hierarquia, formato, exceções."""
    p = Path(cfg.AGENT_MD)
    return p.read_text(encoding="utf-8") if p.exists() else "AGENT.md não encontrado."


@mcp.resource("agent://rules/tools-md")
def get_tools_rules() -> str:
    """Ferramentas disponíveis e como acionar threat intelligence (TOOLS.md)."""
    p = Path(cfg.TOOLS_MD)
    return p.read_text(encoding="utf-8") if p.exists() else "TOOLS.md não encontrado."


@mcp.resource("agent://rules/sop-md")
def get_sop() -> str:
    """Procedimento Operacional Standard — fluxo de 5 etapas (SOP.md)."""
    p = Path(cfg.SOP_MD)
    return p.read_text(encoding="utf-8") if p.exists() else "SOP.md não encontrado."


# ---------------------------------------------------------------------------
# Tools — ações executáveis pelo modelo
# ---------------------------------------------------------------------------

@mcp.tool()
def list_models() -> str:
    """
    Lista todos os modelos de alerta disponíveis em Modelos/.
    Retorna os nomes dos arquivos que podem ser usados como referência.
    """
    modelos_dir = Path(cfg.MODELOS_DIR)
    if not modelos_dir.exists():
        return "Diretório Modelos/ não encontrado."
    nomes = sorted(f.name for f in modelos_dir.iterdir() if f.is_file())
    return "\n".join(nomes) if nomes else "Nenhum modelo encontrado."


@mcp.tool()
def get_model(nome: str) -> str:
    """
    Retorna o conteúdo de um modelo de alerta específico.

    Args:
        nome: Nome exato do arquivo em Modelos/ (ex: "Botnet", "Acesso RDP - Protocolo de Gerenciamento.txt")
    """
    modelos_dir = Path(cfg.MODELOS_DIR)
    # Tenta match exato primeiro, depois busca parcial
    candidatos = list(modelos_dir.glob(f"*{nome}*"))
    if not candidatos:
        return f"Modelo '{nome}' não encontrado em Modelos/."
    path = candidatos[0]
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Erro ao ler modelo: {e}"


@mcp.tool()
def classify_event(fields_json: str, ti_results_json: str = "{}") -> str:
    """
    Executa a análise determinística de um evento de segurança.
    Retorna hipóteses ranqueadas, MITRE candidato, lacunas e próximos passos.

    Args:
        fields_json: JSON com campos extraídos do evento
                     (Horario, Usuario, IP_Origem, Destino, Assunto, LogSource, Acao, IOCs)
        ti_results_json: JSON com resultados de Threat Intelligence {ioc: resultado}
    """
    from soc_copilot.modules.classification_helper import analyze

    try:
        fields = json.loads(fields_json)
        ti_results = json.loads(ti_results_json)
    except json.JSONDecodeError as e:
        return f"Erro no JSON de entrada: {e}"

    result = analyze(fields, ti_results, "")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def analyze_offense(
    payload: str,
    regra: str = "",
    cliente: str = "",
    classificacao: str = "TP",
) -> str:
    """
    Executa o pipeline completo do SOCC em um payload de ofensa.
    Retorna campos extraídos, IOCs, análise determinística e draft gerado.

    Args:
        payload: Texto bruto do payload/log (FortiGate, syslog, JSON, etc.)
        regra:   Nome da regra de detecção (ex: "Acesso RDP Suspeito")
        cliente: Nome do cliente (ex: "Icatu", "EVEREST")
        classificacao: Classificação final (TP, BTP, FP, TN, LTF)
    """
    from soc_copilot.modules import input_adapter, parser_engine, draft_engine
    from soc_copilot.modules.classification_helper import analyze
    from soc_copilot.modules.rule_loader import RulePack

    try:
        fmt, campos, raw = input_adapter.adapt(payload)
        fields = parser_engine.parse(campos, raw)
        analysis = analyze(fields, {}, raw)

        pack = RulePack()
        pack.is_icatu = cliente.lower() == "icatu"
        pack.modelo_nome = regra or "padrao"

        draft, template = draft_engine.generate(classificacao, fields, {}, pack, analysis)

        return json.dumps({
            "formato_detectado": fmt,
            "campos_extraidos": {k: v for k, v in fields.items() if k != "IOCs"},
            "iocs": fields.get("IOCs", {}),
            "classificacao_sugerida": analysis.get("classificacao_sugerida", {}),
            "mitre_candidato": analysis.get("mitre_candidato", {}),
            "hipoteses": analysis.get("hipoteses", []),
            "draft": draft,
            "template_usado": template,
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return f"Erro na análise: {e}"


@mcp.tool()
def query_ti(ioc: str) -> str:
    """
    Consulta reputação de um IOC (IP, domínio ou hash) no VANTAGE.

    Args:
        ioc: Endereço IP, domínio ou hash MD5/SHA1/SHA256
    """
    from soc_copilot.modules.ti_adapter import enrich

    # Detecta tipo
    import re
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", ioc):
        ioc_dict = {"ips_externos": [ioc], "ips_internos": [], "urls": [], "dominios": [], "hashes": []}
    elif re.fullmatch(r"[0-9a-fA-F]{32,64}", ioc):
        ioc_dict = {"ips_externos": [], "ips_internos": [], "urls": [], "dominios": [], "hashes": [ioc]}
    else:
        ioc_dict = {"ips_externos": [], "ips_internos": [], "urls": [], "dominios": [ioc], "hashes": []}

    try:
        results = enrich(ioc_dict)
        return json.dumps(results, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Erro ao consultar TI: {e}"


@mcp.tool()
def get_history(limit: int = 10) -> str:
    """
    Retorna os casos mais recentes analisados pelo SOCC.

    Args:
        limit: Número máximo de casos (padrão: 10, máximo: 50)
    """
    from soc_copilot.modules.persistence import list_runs

    limit = min(max(1, limit), 50)
    try:
        runs = list_runs(limit)
        return json.dumps(runs, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Erro ao consultar histórico: {e}"


@mcp.tool()
def generate_draft(
    classificacao: str,
    fields_json: str,
    analysis_json: str,
    ti_results_json: str = "{}",
    cliente: str = "",
    regra: str = "",
) -> str:
    """
    Gera o texto final de alerta ou nota de encerramento para uma classificação.

    Args:
        classificacao:  TP, BTP, FP, TN ou LTF
        fields_json:    JSON com campos extraídos
        analysis_json:  JSON com resultado da análise (output de classify_event)
        ti_results_json: JSON com resultados de TI
        cliente:        Nome do cliente
        regra:          Nome da regra de detecção
    """
    from soc_copilot.modules.draft_engine import generate
    from soc_copilot.modules.rule_loader import RulePack

    try:
        fields = json.loads(fields_json)
        analysis = json.loads(analysis_json)
        ti_results = json.loads(ti_results_json)
    except json.JSONDecodeError as e:
        return f"Erro no JSON de entrada: {e}"

    pack = RulePack()
    pack.is_icatu = cliente.lower() == "icatu"
    pack.modelo_nome = regra or "padrao"

    try:
        draft, template = generate(classificacao, fields, ti_results, pack, analysis)
        return f"Template: {template}\n\n{draft}"
    except Exception as e:
        return f"Erro na geração do draft: {e}"


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run()
