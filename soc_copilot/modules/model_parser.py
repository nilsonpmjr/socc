"""
model_parser.py
Extrai fragmentos reutilizáveis dos modelos reais em Modelos/.

O acervo de alertas reais é o "conhecimento acumulado" do SOC.
Este módulo o torna acessível ao draft_engine de forma estruturada:
  - frase de abertura (padrão narrativo do tipo de ameaça)
  - parágrafo MITRE em Português técnico já validado
  - técnica MITRE identificada (T1234 / T1234.001)
  - referência completa conforme padrão do modelo
  - recomendação do modelo (base para anonimização)

Nenhum dado real do evento é extraído — apenas os padrões de linguagem
e conhecimento técnico que os analistas já consolidaram.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Estrutura de fragmentos extraídos
# ---------------------------------------------------------------------------

@dataclass
class ModelFragments:
    nome: str = ""
    abertura: str = ""          # frase inicial identificando a ameaça
    mitre_descricao: str = ""   # parágrafo técnico MITRE em Português
    mitre_tecnica: str = ""     # T1234 ou T1234.001
    mitre_referencia: str = ""  # linha "Referência: ..." completa
    recomendacao: str = ""      # parágrafo "Recomendamos..."
    raw_blocos: list[str] = field(default_factory=list)  # parágrafos originais


# ---------------------------------------------------------------------------
# Regexes de extração
# ---------------------------------------------------------------------------

_RE_MITRE_TECNICA = re.compile(r"\b(T\d{4}(?:\.\d{3})?)\b")
_RE_REFERENCIA_LINE = re.compile(
    r"^Refer[eê]ncia[:\s].*T\d{4}", re.IGNORECASE
)
_RE_RECOMENDACAO = re.compile(
    r"^Recomenda(mos|[-\s]se|r)", re.IGNORECASE
)
_RE_ABERTURA = re.compile(
    r"^(Identificad[ao]|Foi identificad[ao]|Detectad[ao]|"
    r"Identific[oa]mos|Constatad[ao]|Observad[ao])",
    re.IGNORECASE,
)

# Indicadores de parágrafo técnico MITRE (sem ser a linha de referência)
_MITRE_MARKERS = (
    "adversários", "adversarios",
    "mitre", "att&ck", "att&amp;ck",
    "técnica", "tecnica",
    "sub-technique", "sub-técnica",
)

# Blocos de detalhe estruturado a ignorar (não são parágrafos narrativos)
_DETAIL_PREFIXES = (
    "usuário:", "usuario:", "host:", "ip de origem:",
    "destino:", "arquivo:", "diretório:", "log source:",
    "porta:", "protocolo:", "devname:", "breach details:",
    "modelo darktrace:", "crowdstrike link:", "event id",
)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _split_blocos(texto: str) -> list[str]:
    """Divide o texto em parágrafos não-vazios, normalizando espaços."""
    raw = texto.replace("\r\n", "\n").replace("\r", "\n")
    blocos = [b.strip() for b in re.split(r"\n{2,}", raw)]
    return [b for b in blocos if b]


def _is_detail_line(bloco: str) -> bool:
    """Retorna True se o bloco parece um detalhe estruturado (label: valor)."""
    primeira = bloco.split("\n")[0].lower()
    return any(primeira.startswith(p) for p in _DETAIL_PREFIXES)


def _is_boilerplate(bloco: str) -> bool:
    """Retorna True para linhas de boilerplate que não têm valor como fragmento."""
    lower = bloco.lower().strip()
    return lower in {
        "prezados,", "prezados", "segue em anexo o payload.",
        "segue em anexo o payload", "em anexo o payload.",
        "em anexo o payload", "segue anexo payload.",
        "segue anexo payload", "segue em anexo payload da ofensa.",
    } or lower.startswith("segue") and "payload" in lower


def _extract_mitre_tecnica(texto: str) -> str:
    """Extrai o primeiro código T1234[.001] encontrado no texto."""
    m = _RE_MITRE_TECNICA.search(texto)
    return m.group(1) if m else ""


def _find_referencia_line(blocos: list[str]) -> str:
    """Encontra e retorna a linha/bloco de Referência MITRE."""
    for bloco in blocos:
        for linha in bloco.split("\n"):
            if _RE_REFERENCIA_LINE.match(linha.strip()):
                return linha.strip()
    return ""


def _find_mitre_descricao(blocos: list[str]) -> str:
    """
    Identifica o parágrafo técnico que descreve a técnica MITRE.
    É o bloco que menciona palavras-chave MITRE mas NÃO é a linha de referência.
    """
    candidatos = []
    for bloco in blocos:
        if _is_boilerplate(bloco) or _is_detail_line(bloco):
            continue
        lower = bloco.lower()
        if _RE_REFERENCIA_LINE.match(bloco.strip()):
            continue
        if any(m in lower for m in _MITRE_MARKERS) and len(bloco) > 60:
            candidatos.append(bloco)

    if not candidatos:
        return ""

    # Prefere o mais longo (mais completo) que não seja a recomendação
    candidatos_sem_rec = [
        c for c in candidatos
        if not _RE_RECOMENDACAO.match(c.strip())
    ]
    pool = candidatos_sem_rec or candidatos
    return max(pool, key=len)


def _find_recomendacao(blocos: list[str]) -> str:
    """Encontra o parágrafo de recomendação."""
    for bloco in blocos:
        if _RE_RECOMENDACAO.match(bloco.strip()):
            return bloco.strip()
    return ""


def _find_abertura(blocos: list[str]) -> str:
    """
    Encontra a frase de abertura — primeira sentença substantiva
    após 'Prezados,' que identifica o tipo de ameaça.
    """
    passou_prezados = False
    for bloco in blocos:
        lower = bloco.lower().strip()
        if lower.startswith("prezados"):
            passou_prezados = True
            continue
        if not passou_prezados:
            continue
        if _is_boilerplate(bloco) or _is_detail_line(bloco):
            continue
        # Pega apenas a primeira frase do bloco (até o primeiro ponto final)
        primeira_frase = bloco.split(".")[0].strip()
        if len(primeira_frase) > 20:
            return primeira_frase + "."
    return ""


def _anonymize(texto: str) -> str:
    """
    Remove referências específicas que não devem vazar para outros casos:
    - nomes de usuários
    - IPs
    - hostnames específicos
    - números de ticket
    Preserva o padrão de linguagem e as orientações gerais.
    """
    if not texto:
        return texto

    # Remove IPs (IPv4)
    texto = re.sub(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "o ativo envolvido", texto)

    # Remove endereços de email
    texto = re.sub(r"\b[\w.+-]+@[\w.-]+\.\w+\b", "o usuário envolvido", texto)

    # Remove tickets (#12345 ou Ticket #12345)
    texto = re.sub(r"[Tt]icket\s*#?\d+|#\d{4,}", "", texto)

    # Remove hostnames estilo HOSTNAME-XXXXX (maiúsculas com hífens e números)
    texto = re.sub(r"\b[A-Z]{2,}[-_][A-Z0-9]{3,}\b", "o host envolvido", texto)

    # Remove nomes de usuário no formato nome.sobrenome
    texto = re.sub(r'\b[a-z]{2,}\.[a-z]{2,}\b', "o usuário envolvido", texto)

    # Limpa múltiplos espaços
    texto = re.sub(r" {2,}", " ", texto)

    return texto.strip()


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def parse(caminho: str | Path) -> ModelFragments:
    """
    Lê um arquivo de modelo e extrai seus fragmentos reutilizáveis.
    Retorna ModelFragments vazio se o arquivo não existir ou não for parseable.
    """
    path = Path(caminho)
    if not path.exists() or not path.is_file():
        return ModelFragments(nome=path.name)

    try:
        texto = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ModelFragments(nome=path.name)

    blocos = _split_blocos(texto)

    abertura     = _find_abertura(blocos)
    mitre_desc   = _find_mitre_descricao(blocos)
    ref_line     = _find_referencia_line(blocos)
    recomendacao = _find_recomendacao(blocos)

    # Extrai técnica do texto completo (não só da linha de referência)
    mitre_tecnica = _extract_mitre_tecnica(ref_line or mitre_desc or texto)

    return ModelFragments(
        nome=path.name,
        abertura=abertura,
        mitre_descricao=mitre_desc,
        mitre_tecnica=mitre_tecnica,
        mitre_referencia=ref_line,
        recomendacao=_anonymize(recomendacao),
        raw_blocos=blocos,
    )


def parse_all(modelos_dir: str | Path) -> dict[str, ModelFragments]:
    """
    Parseia todos os modelos de um diretório.
    Retorna dict {nome_arquivo: ModelFragments}.
    """
    diretorio = Path(modelos_dir)
    resultado: dict[str, ModelFragments] = {}
    if not diretorio.exists():
        return resultado
    for p in diretorio.iterdir():
        if p.is_file():
            fragmentos = parse(p)
            if fragmentos.mitre_tecnica or fragmentos.recomendacao:
                resultado[p.name] = fragmentos
    return resultado
