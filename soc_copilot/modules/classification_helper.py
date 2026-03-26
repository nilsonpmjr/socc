"""
classification_helper.py
Organiza os fatos observados, sugere hipóteses e lacunas,
e prepara o pacote de dados para o draft_engine.

Opera em modo determinístico:
  - pontua cada classificação candidata com base em sinais extraídos
    (keywords ponderadas, resultados de Threat Intelligence, campos presentes)
  - infere técnica MITRE candidata pelo nome da regra, log source e payload
  - aponta campos ausentes como lacunas
  - gera próximos passos contextuais por classificação
  - gera alertas de qualidade baseados em evidências disponíveis
  - não toma decisão final (a classificação final é sempre do analista)
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Sinais ponderados por classificação — (keyword, peso)
# Peso maior = sinal mais forte para aquela hipótese
# ---------------------------------------------------------------------------

_LTF_SIGNALS: list[tuple[str, int]] = [
    ("log transmission failure", 4),
    ("ltf", 4),
    ("sem eventos", 3),
    ("no events", 3),
    ("falha na coleta", 4),
    ("log gap", 3),
    ("sem logs", 3),
    ("falha de transmissao", 4),
    ("falha de transmissão", 4),
    ("transmission failure", 4),
    ("events not received", 3),
    ("no data received", 3),
    ("agent offline", 3),
    ("collector offline", 3),
    ("syslog unreachable", 3),
    ("no log source", 3),
    ("fonte de log indisponivel", 3),
    ("fonte indisponivel", 3),
    ("data loss detected", 3),
    ("connection lost", 2),
]

_FP_SIGNALS: list[tuple[str, int]] = [
    ("scanner interno", 4),
    ("vulnerability scan", 4),
    ("nessus", 4),
    ("qualys", 4),
    ("tenable", 4),
    ("rapid7", 4),
    ("openvas", 4),
    ("pentest", 4),
    ("teste de penetracao", 4),
    ("teste de penetração", 4),
    ("red team", 3),
    ("security assessment", 3),
    ("authorized scan", 4),
    ("varredura autorizada", 4),
    ("patch scan", 3),
    ("compliance scan", 3),
    ("gmud", 4),
    ("change management", 4),
    ("janela de mudanca", 4),
    ("janela de mudança", 4),
    ("backup", 3),
    ("monitoramento", 2),
    ("asset discovery", 3),
    ("inventory scan", 3),
    ("network discovery", 3),
]

_BTP_SIGNALS: list[tuple[str, int]] = [
    ("atividade esperada", 4),
    ("autorizado", 4),
    ("whitelist", 4),
    ("legitimo", 4),
    ("légitimo", 4),
    ("legítimo", 4),
    ("excecao", 3),
    ("exceção", 3),
    ("exception", 3),
    ("aprovado", 3),
    ("approved", 3),
    ("known behavior", 4),
    ("comportamento conhecido", 4),
    ("service account", 3),
    ("conta de servico", 3),
    ("conta de serviço", 3),
    ("admin", 2),
    ("administrador", 3),
    ("automacao", 2),
    ("automação", 2),
    ("ci/cd", 3),
    ("devops", 2),
    ("deployment", 2),
    ("deploy", 2),
    ("maintenance window", 3),
    ("janela de manutencao", 3),
    ("janela de manutenção", 3),
    ("false alert", 3),
    ("alerta esperado", 4),
]

# ---------------------------------------------------------------------------
# Organizações de scanning conhecidas — presença no TI result indica BTP
# ---------------------------------------------------------------------------

_KNOWN_SCANNER_ORGS = {
    "tenable", "nessus", "qualys", "rapid7", "openvas", "greenbone",
    "shodan", "censys", "zmap", "masscan", "acunetix", "veracode",
    "checkmarx", "burp suite", "nikto", "w3af",
    "internet-measurement", "research scanning",
}

# Ações que indicam que o controle de segurança já bloqueou o tráfego
_BLOCKED_ACTIONS = {"dropped", "blocked", "reset", "deny", "denied", "rejected", "drop", "block"}

# ---------------------------------------------------------------------------
# Palavras-chave para interpretar veredito da Threat Intelligence
# ---------------------------------------------------------------------------

_TI_MALICIOUS_KEYWORDS = (
    "malicious", "malicioso", "malware", "trojan", "botnet",
    "ransomware", "phishing", "exploit", "c2", "command and control",
    "threat", "ameaca", "ameaça", "compromised", "comprometido",
)
_TI_SUSPICIOUS_KEYWORDS = (
    "suspicious", "suspeito", "potentially unwanted", "potentially malicious",
    "high risk", "alto risco", "moderate risk", "medium risk",
)
_TI_CLEAN_KEYWORDS = (
    "clean", "limpo", "safe", "seguro", "benign", "benigno",
    "no threats", "sem ameacas", "sem ameaças", "legitimate", "legitimo",
    "legítimo", "low risk", "baixo risco",
)

# ---------------------------------------------------------------------------
# Mapeamento MITRE ATT&CK — (keywords, técnica, justificativa)
# Ordenado do mais específico para o mais genérico
# ---------------------------------------------------------------------------

_MITRE_MAPPINGS: list[tuple[tuple[str, ...], str, str]] = [
    # Exploração de aplicação pública (Log4Shell, Log4j, CVEs web)
    (("log4j", "log4shell", "log4", "jndi", "cve-2021-44228",
      "exploit public", "exploit web", "web exploit", "rce via",
      "apache struts", "spring4shell", "shellshock", "heartbleed",
      "sql injection", "sqli", "remote code execution", "rce",
      "path traversal", "directory traversal", "../", "lfi", "rfi"),
     "T1190", "Tentativa de exploração de vulnerabilidade em aplicação pública detectada."),
    # DoS/DDoS de endpoint ou rede
    (("denial of service", "ddos", "dos attack", "flood", "syn flood",
      "amplification", "udp flood", "http flood", "layer 7",
      ".dos", "dos}", "dos\"", " dos "),
     "T1499", "Ataque de negação de serviço direcionado a endpoint ou serviço detectado."),
    # Despejo de credenciais
    (("mimikatz", "lsass", "credential dump", "ntds.dit"), "T1003",
     "Despejo de credenciais do sistema operacional identificado."),
    # Brute force
    (("brute force", "brute-force", "password spray", "forca bruta", "força bruta",
      "tentativas de login", "login attempts", "failed logon", "failed login",
      "account lockout", "conta bloqueada"),
     "T1110", "Tentativa de força bruta ou pulverização de senhas detectada."),
    # Kerberos
    (("kerberoasting", "kerberos", "golden ticket", "silver ticket", "ticket granting"),
     "T1558.003", "Abuso de autenticação Kerberos identificado."),
    # Pass-the-Hash
    (("pass the hash", "pass-the-hash", "pth attack"), "T1550.002",
     "Técnica Pass-the-Hash detectada no ambiente."),
    # Escalação de privilégios
    (("privilege escalation", "escalacao de privilegio", "escalação de privilégio",
      "uac bypass", "bypass uac", "token impersonation"),
     "T1548.002", "Tentativa de escalação de privilégios ou bypass de UAC detectada."),
    (("sudo abuse", "setuid", "sudoers"), "T1548.001",
     "Abuso de mecanismo de elevação de privilégios em ambiente Linux detectado."),
    # Injeção de processo
    (("process injection", "dll injection", "code injection", "dll hijack", "dll hijacking"),
     "T1055", "Injeção de código em processo legítimo detectada."),
    # RDP
    (("rdp", "remote desktop protocol", "mstsc", "3389"),
     "T1021.001", "Acesso via Remote Desktop Protocol identificado."),
    # SMB / PsExec
    (("smb", "psexec", "admin$", "ipc$", "windows admin share"),
     "T1021.002", "Movimentação lateral via SMB ou ferramenta de administração remota detectada."),
    # SSH
    (("ssh", "secure shell", "sftp", "port 22"),
     "T1021.004", "Uso de SSH para acesso remoto ou movimentação lateral identificado."),
    # WMI
    (("wmi", "windows management instrumentation", "wmic", "wmiprvse"),
     "T1047", "Execução remota via WMI detectada."),
    # Movimentação lateral genérica
    (("lateral movement", "movimentacao lateral", "movimentação lateral",
      "east-west", "internal scan"),
     "T1021", "Indicativo de movimentação lateral entre sistemas internos."),
    # PowerShell
    (("powershell", "ps1", "powershell.exe", "pwsh"),
     "T1059.001", "Execução de scripts PowerShell detectada."),
    # Cmd / Batch
    (("cmd.exe", "command prompt", "batch script", ".bat", "net.exe", "wscript"),
     "T1059.003", "Execução via linha de comando do Windows detectada."),
    # Scripts genéricos
    (("python", "perl", "ruby", "bash script", "sh script"),
     "T1059", "Execução de scripts via interpretador de linguagem detectada."),
    # Macros Office
    (("macro", "vba", "office macro", "excel macro", "word macro"),
     "T1137", "Uso de macros maliciosas em documentos Office detectado."),
    # Phishing
    (("phishing", "spear phishing", "spearphishing"),
     "T1566", "Indicativo de ataque de phishing detectado."),
    (("malicious attachment", "anexo malicioso", "malicious email"),
     "T1566.001", "Anexo malicioso identificado em e-mail."),
    (("malicious link", "link malicioso", "malicious url", "malicious href"),
     "T1566.002", "Link malicioso identificado em e-mail ou mensagem."),
    # Ofuscação
    (("obfuscation", "ofuscacao", "ofuscação", "encoded command",
      "base64 encoded", "encoded payload", "xor encoded"),
     "T1027", "Técnica de ofuscação ou codificação de payload detectada."),
    # Desabilitação de controles
    (("disable antivirus", "disable security", "desabilitar antivirus",
      "disable logging", "desabilitar log", "disable firewall", "tamper"),
     "T1562", "Tentativa de desabilitar controles de segurança detectada."),
    # Mascaramento
    (("masquerading", "processo mascarado", "process masquerading",
      "renamed binary", "executable renamed"),
     "T1036", "Tentativa de mascaramento de processo ou arquivo detectada."),
    # Tarefa agendada
    (("scheduled task", "tarefa agendada", "at.exe", "schtasks"),
     "T1053.005", "Criação de tarefa agendada para persistência detectada."),
    # Registro para persistência
    (("registry run", "run key", "hkcu\\software\\microsoft\\windows\\currentversion\\run",
      "hklm\\software\\microsoft\\windows\\currentversion\\run", "chave de registro"),
     "T1547.001", "Modificação de chave de registro para persistência identificada."),
    # Serviço para persistência
    (("new service", "novo servico", "service created", "sc.exe create"),
     "T1543.003", "Criação de serviço para persistência detectada."),
    # C2 genérico
    (("command and control", "c2 communication", "beacon", "beaconing",
      "callback", "c&c"),
     "T1071", "Comunicação de comando e controle identificada."),
    # DNS tunelamento
    (("dns tunneling", "dns exfiltration", "dns query anomaly", "dns anomaly",
      "high volume dns", "dns over https"),
     "T1071.004", "Uso anômalo de DNS para comunicação ou exfiltração detectado."),
    # HTTP C2
    (("http beacon", "https beacon", "web request anomaly", "suspicious http",
      "http tunnel"),
     "T1071.001", "Comunicação C2 via protocolo HTTP/HTTPS identificada."),
    # Exfiltração
    (("exfiltration", "exfiltracao", "exfiltração", "data theft",
      "roubo de dados", "data exfil", "large upload", "unusual upload"),
     "T1041", "Indicativo de exfiltração de dados detectado."),
    # Varredura de rede
    (("network scan", "port scan", "varredura de rede", "nmap", "masscan",
      "host discovery", "ping sweep"),
     "T1046", "Varredura de rede ou descoberta de serviços detectada."),
    # Enumeração de contas
    (("account enumeration", "user enumeration", "enumeracao de usuarios",
      "ldap query", "net user", "net localgroup"),
     "T1087", "Enumeração de contas de usuário detectada."),
    # Descoberta de sistema
    (("system discovery", "system info", "systeminfo", "net view",
      "nltest", "ipconfig", "whoami"),
     "T1082", "Coleta de informações sobre o sistema alvo detectada."),
    # Ransomware
    (("ransomware", "file encryption", "arquivos criptografados",
      "ransom note", "criptografado", "decrypt", ".locked", ".encrypted"),
     "T1486", "Atividade de ransomware ou criptografia maliciosa de arquivos detectada."),
    # DoS
    (("denial of service", "ddos", "dos attack", "flood", "syn flood",
      "amplification"),
     "T1498", "Ataque de negação de serviço detectado."),
    # Destruição de dados
    (("data destruction", "wiper", "disk wipe", "destruicao de dados",
      "destruição de dados"),
     "T1485", "Atividade de destruição de dados detectada."),
    # Viagem impossível / conta válida
    (("impossible travel", "viagem impossivel", "viagem impossível",
      "anomalous login", "login anomalo", "login anômalo",
      "geographic anomaly", "simultaneus login", "simultaneous login"),
     "T1078",
     "Uso anômalo de credenciais legítimas — possível comprometimento de conta."),
    (("account compromise", "conta comprometida", "credential theft",
      "stolen credential"),
     "T1078",
     "Possível comprometimento ou uso indevido de conta legítima detectado."),
]

# ---------------------------------------------------------------------------
# Próximos passos contextuais por classificação
# ---------------------------------------------------------------------------

_PROXIMOS_PASSOS: dict[str, list[str]] = {
    "TP": [
        "Isolar o ativo afetado caso haja confirmação adicional de comprometimento.",
        "Coletar e preservar logs complementares do período para análise de escopo.",
        "Escalar para o time de resposta a incidentes conforme o procedimento interno.",
        "Revisar acessos, credenciais e sessões ativas relacionadas ao evento.",
        "Verificar se há movimentação lateral associada ao mesmo período.",
    ],
    "FP": [
        "Avaliar ajuste ou criação de exceção na regra de detecção para reduzir reincidência.",
        "Documentar o contexto justificante e registrar para auditoria futura.",
        "Verificar se a regra precisa de refinamento de escopo ou condição de exceção.",
    ],
    "BTP": [
        "Documentar a justificativa técnica da benignidade para o histórico operacional.",
        "Verificar se o comportamento observado pode ser adicionado à lista de exceções.",
        "Encerrar o caso e manter o monitoramento regular do ativo.",
    ],
    "TN": [
        "Encerrar o caso e manter o monitoramento contínuo conforme o fluxo operacional.",
        "Registrar o contexto para suporte à calibração futura da regra.",
    ],
    "LTF": [
        "Acionar o responsável técnico pela fonte de logs para validar coleta e transmissão.",
        "Verificar conectividade e disponibilidade do agente ou conector da fonte de logs.",
        "Checar se há janela de manutenção ou mudança ativa que justifique a ausência.",
        "Aguardar normalização da coleta antes de reanalisar o período afetado.",
        "Abrir chamado com o time de infraestrutura caso a indisponibilidade persista.",
    ],
}

# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------


def _weighted_score(signals: list[tuple[str, int]], raw_lower: str) -> int:
    return sum(weight for keyword, weight in signals if keyword in raw_lower)


def _classify_ti_result(result: str) -> str:
    """Interpreta um resultado de TI e retorna 'malicious', 'suspicious', 'clean' ou 'unknown'."""
    if not result:
        return "unknown"
    if "[aviso]" in result.lower() or "[erro]" in result.lower():
        return "failed"

    result_lower = result.lower()
    if any(k in result_lower for k in _TI_MALICIOUS_KEYWORDS):
        return "malicious"
    if any(k in result_lower for k in _TI_SUSPICIOUS_KEYWORDS):
        return "suspicious"
    if any(k in result_lower for k in _TI_CLEAN_KEYWORDS):
        return "clean"

    # Tenta extrair score numérico quando veredito textual não basta
    score_match = re.search(r"score[:\s]+(\d+)", result_lower)
    if score_match:
        score = int(score_match.group(1))
        if score >= 70:
            return "malicious"
        if score >= 40:
            return "suspicious"
        if score < 20:
            return "clean"

    return "unknown"


def _parse_ti_verdicts(ti_results: dict) -> dict[str, int]:
    """Conta vereditos de TI por categoria."""
    counts: dict[str, int] = {
        "malicious": 0, "suspicious": 0, "clean": 0, "unknown": 0, "failed": 0,
    }
    for result in (ti_results or {}).values():
        verdict = _classify_ti_result(result)
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts


def _map_mitre(raw_text: str, fields: dict) -> dict:
    """
    Infere técnica MITRE candidata a partir de keywords no texto bruto e campos.
    Extrai também referências explícitas no formato T1234 ou T1234.001.
    """
    search_text = " ".join([
        raw_text,
        fields.get("Assunto", ""),
        fields.get("LogSource", ""),
        fields.get("Caminho", ""),
    ]).lower()

    # Extração explícita: T1234 ou T1234.001 já mencionados no payload ou regra
    explicit = re.search(r"\b(T\d{4}(?:\.\d{3})?)\b", raw_text + " " + fields.get("Assunto", ""))
    if explicit:
        tecnica = explicit.group(1)
        return {
            "tecnica": tecnica,
            "justificativa": (
                f"Técnica {tecnica} explicitamente referenciada no payload ou nome da regra."
            ),
        }

    for keywords, tecnica, justificativa in _MITRE_MAPPINGS:
        if any(kw in search_text for kw in keywords):
            return {"tecnica": tecnica, "justificativa": justificativa}

    return {"tecnica": "", "justificativa": ""}


def _build_o_que(fields: dict, raw_text: str) -> str:
    """Constrói descrição factual do evento a partir dos campos disponíveis."""
    assunto = (fields.get("Assunto") or "").strip()
    log_source = (fields.get("LogSource") or "").strip()

    if assunto and assunto.lower() not in {"n/a", "none", "null", ""}:
        if log_source and log_source.lower() not in {"n/a", "none", "null", ""}:
            return f"Alerta '{assunto}' gerado pela fonte '{log_source}'."
        return f"Alerta '{assunto}' detectado no ambiente monitorado."

    if log_source and log_source.lower() not in {"n/a", "none", "null", ""}:
        return f"Evento de segurança detectado pela fonte de logs '{log_source}'."

    # Fallback: usa as primeiras palavras do payload para dar contexto mínimo
    primeiras = " ".join(raw_text.split()[:12]).strip()
    if primeiras:
        return f"Evento detectado: {primeiras[:120]}."
    return "Evento de segurança detectado no ambiente monitorado."


def _build_artefatos(fields: dict) -> list[str]:
    iocs = fields.get("IOCs", {})
    return (
        iocs.get("ips_externos", [])
        + iocs.get("dominios", [])
        + iocs.get("hashes", [])
    )


def _score_hipoteses(fields: dict, ti_results: dict, raw_text: str) -> list[dict]:
    raw_lower = raw_text.lower()

    # Combina payload + resultado TI para busca de sinais — resolve o caso onde
    # a organização (ex: Tenable) aparece apenas no TI result, não no payload original
    ti_text = " ".join((ti_results or {}).values()).lower()
    combined_lower = raw_lower + " " + ti_text

    acao = (fields.get("Acao") or "").strip().lower()
    ja_bloqueado = acao in _BLOCKED_ACTIONS

    hipoteses = []
    ti_counts = _parse_ti_verdicts(ti_results)

    # Scanner org detectado no resultado de TI (ex: ISP=Tenable, domain=tenable.com)
    scanner_no_ti = any(org in ti_text for org in _KNOWN_SCANNER_ORGS)

    # --- Log Transmission Failure ---
    ltf_score = _weighted_score(_LTF_SIGNALS, combined_lower)
    if ltf_score:
        confianca = min(round(0.35 + ltf_score * 0.08, 2), 0.92)
        hipoteses.append({
            "tipo": "Log Transmission Failure",
            "confianca": confianca,
            "justificativa": "Sinais de falha na transmissão ou coleta de logs detectados no payload.",
        })

    # --- Benign True Positive por scanner org no TI (alta prioridade) ---
    if scanner_no_ti:
        # Scanner bloqueado + TI limpo → BTP de alta confiança
        confianca_btp = 0.88 if ja_bloqueado else 0.72
        org_detectada = next((o for o in _KNOWN_SCANNER_ORGS if o in ti_text), "scanner de segurança")
        hipoteses.append({
            "tipo": "Benign True Positive",
            "confianca": confianca_btp,
            "justificativa": (
                f"Threat Intelligence identificou o IP de origem como pertencente a '{org_detectada}', "
                f"ferramenta de varredura de segurança conhecida."
                + (" Tráfego já bloqueado pelo controle de segurança." if ja_bloqueado else "")
                + " Atividade esperada de scanner de vulnerabilidades — regra disparou corretamente."
            ),
        })

    # --- False Positive ---
    fp_score = _weighted_score(_FP_SIGNALS, combined_lower)
    if fp_score:
        confianca = min(round(0.3 + fp_score * 0.06, 2), 0.85)
        # TI clean reforça FP
        if ti_counts.get("clean", 0) > 0 and ti_counts.get("malicious", 0) == 0:
            confianca = min(confianca + 0.10, 0.90)
        hipoteses.append({
            "tipo": "False Positive",
            "confianca": confianca,
            "justificativa": (
                "Payload contém termos associados a ferramentas ou processos "
                "operacionais internos conhecidos (varredura, backup, GMUD, etc.)."
            ),
        })

    # --- Benign True Positive (sinais gerais) ---
    btp_score = _weighted_score(_BTP_SIGNALS, combined_lower)
    if btp_score:
        confianca = min(round(0.3 + btp_score * 0.07, 2), 0.88)
        if ti_counts.get("clean", 0) > 0 and ti_counts.get("malicious", 0) == 0:
            confianca = min(confianca + 0.08, 0.90)
        # Ação bloqueada + veredito limpo reforça BTP
        if ja_bloqueado and ti_counts.get("malicious", 0) == 0:
            confianca = min(confianca + 0.06, 0.90)
        hipoteses.append({
            "tipo": "Benign True Positive",
            "confianca": confianca,
            "justificativa": (
                "Atividade parece legítima e contextualmente esperada, "
                "mas foi corretamente disparada pela regra de detecção."
            ),
        })

    # --- True Positive ---
    iocs = fields.get("IOCs", {})
    tem_ioc_ext = bool(
        iocs.get("ips_externos") or iocs.get("dominios") or iocs.get("hashes")
    )

    if ti_counts.get("malicious", 0) > 0:
        # TI confirma ameaça: alta confiança de TP
        n_maliciosos = ti_counts["malicious"]
        confianca_tp = min(round(0.65 + n_maliciosos * 0.08, 2), 0.95)
        tipos_ioc = _descricao_iocs(iocs)
        hipoteses.append({
            "tipo": "True Positive",
            "confianca": confianca_tp,
            "justificativa": (
                f"Threat Intelligence confirmou {n_maliciosos} artefato(s) malicioso(s) "
                f"({tipos_ioc}). Evidência de ameaça real detectada."
            ),
        })
    elif ti_counts.get("suspicious", 0) > 0:
        confianca_tp = min(round(0.55 + ti_counts["suspicious"] * 0.05, 2), 0.75)
        hipoteses.append({
            "tipo": "True Positive",
            "confianca": confianca_tp,
            "justificativa": (
                "Threat Intelligence retornou veredito suspeito para artefato(s) consultado(s). "
                "Investigação adicional necessária para confirmação."
            ),
        })
    elif tem_ioc_ext and not ti_results:
        # IOC externo sem consulta TI ainda
        tipos_ioc = _descricao_iocs(iocs)
        hipoteses.append({
            "tipo": "True Positive",
            "confianca": 0.50,
            "justificativa": (
                f"{tipos_ioc} identificado(s) no payload; "
                "reputação via Threat Intelligence necessária para confirmar."
            ),
        })
    elif tem_ioc_ext and ti_counts.get("clean", 0) > 0 and ti_counts.get("malicious", 0) == 0:
        # IOC externo, mas TI retornou clean — baixa probabilidade de TP
        hipoteses.append({
            "tipo": "True Positive",
            "confianca": 0.20,
            "justificativa": (
                "IOC(s) externo(s) identificado(s), porém Threat Intelligence "
                "retornou veredito limpo. Probabilidade de TP reduzida."
            ),
        })
    elif tem_ioc_ext:
        tipos_ioc = _descricao_iocs(iocs)
        hipoteses.append({
            "tipo": "True Positive",
            "confianca": 0.50,
            "justificativa": (
                f"{tipos_ioc} identificado(s); análise de reputação pendente."
            ),
        })

    return sorted(hipoteses, key=lambda h: h["confianca"], reverse=True)


def _descricao_iocs(iocs: dict) -> str:
    tipos: list[str] = []
    if iocs.get("ips_externos"):
        n = len(iocs["ips_externos"])
        tipos.append(f"{n} IP(s) externo(s)")
    if iocs.get("dominios"):
        n = len(iocs["dominios"])
        tipos.append(f"{n} domínio(s)")
    if iocs.get("hashes"):
        n = len(iocs["hashes"])
        tipos.append(f"{n} hash(es)")
    return ", ".join(tipos) if tipos else "Indicador(es) externo(s)"


def _aponta_lacunas(fields: dict, ti_results: dict) -> list[str]:
    lacunas = []

    for campo, descricao in [
        ("Horario", "Horário do evento"),
        ("Usuario", "Identidade do ator"),
        ("IP_Origem", "IP de origem"),
        ("LogSource", "Fonte de logs"),
    ]:
        if not fields.get(campo) or str(fields.get(campo, "")).strip().upper() in {"N/A", "NONE", "NULL", ""}:
            lacunas.append(f"{descricao} ausente — análise parcialmente comprometida.")

    iocs = fields.get("IOCs", {})
    tem_ext = bool(iocs.get("ips_externos") or iocs.get("dominios") or iocs.get("hashes"))

    if tem_ext and not ti_results:
        lacunas.append(
            "IOC(s) externo(s) identificado(s), mas consulta de Threat Intelligence não foi realizada."
        )

    ti_counts = _parse_ti_verdicts(ti_results)
    total_ti = sum(ti_counts.values())
    failed_ti = ti_counts.get("failed", 0)
    if total_ti > 0 and failed_ti == total_ti:
        lacunas.append(
            "Todas as consultas de Threat Intelligence falharam; reputação dos artefatos não confirmada."
        )
    elif total_ti > 0 and failed_ti > 0:
        lacunas.append(
            f"{failed_ti} de {total_ti} consulta(s) de TI falharam; alguns artefatos sem reputação confirmada."
        )

    if not iocs.get("ips_externos") and not iocs.get("dominios") and not iocs.get("hashes"):
        if not iocs.get("ips_internos"):
            lacunas.append("Nenhum artefato de rede identificado; rastreamento de origem e destino limitado.")

    return lacunas


def _build_alertas_qualidade(
    fields: dict, hipoteses: list[dict], ti_results: dict, raw_text: str
) -> list[str]:
    alertas: list[str] = []

    # Confiança baixa na melhor hipótese
    if hipoteses:
        melhor_confianca = hipoteses[0].get("confianca", 0.0)
        if melhor_confianca < 0.40:
            alertas.append(
                "Confiança baixa na classificação sugerida — validação humana fortemente recomendada."
            )
        # Hipóteses com confiança muito próximas (ambiguidade)
        if len(hipoteses) >= 2:
            diff = abs(hipoteses[0].get("confianca", 0) - hipoteses[1].get("confianca", 0))
            if diff < 0.10:
                alertas.append(
                    "Múltiplas hipóteses com confiança similar — evidências adicionais recomendadas para conclusão."
                )
    else:
        alertas.append("Nenhum sinal suficiente para sugestão automática de classificação.")

    # Payload muito curto (pode ser truncado)
    if len(raw_text.strip()) < 80:
        alertas.append("Payload muito curto; pode estar truncado ou incompleto.")

    # TI sem resultado útil quando há IOCs externos
    iocs = fields.get("IOCs", {})
    tem_ext = bool(iocs.get("ips_externos") or iocs.get("dominios") or iocs.get("hashes"))
    ti_counts = _parse_ti_verdicts(ti_results)
    if tem_ext and ti_counts.get("failed", 0) == sum(ti_counts.values()) and ti_results:
        alertas.append("Consultas de TI falharam para todos os IOCs — enriquecimento indisponível.")

    return alertas


def _build_proximos_passos(hipoteses: list[dict]) -> list[str]:
    if not hipoteses:
        return _PROXIMOS_PASSOS.get("TN", [])
    tipo_principal = hipoteses[0].get("tipo", "")
    mapa = {
        "True Positive": "TP",
        "False Positive": "FP",
        "Benign True Positive": "BTP",
        "True Negative": "TN",
        "Log Transmission Failure": "LTF",
    }
    chave = mapa.get(tipo_principal, "TN")
    return _PROXIMOS_PASSOS.get(chave, [])


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def analyze(fields: dict, ti_results: dict, raw_text: str) -> dict:
    """
    Retorna o pacote estruturado de apoio à análise.
    Não decide a classificação final — apenas sugere.
    """
    hipoteses = _score_hipoteses(fields, ti_results, raw_text)
    lacunas = _aponta_lacunas(fields, ti_results)
    mitre = _map_mitre(raw_text, fields)
    alertas = _build_alertas_qualidade(fields, hipoteses, ti_results, raw_text)
    proximos = _build_proximos_passos(hipoteses)
    artefatos = _build_artefatos(fields)
    o_que = _build_o_que(fields, raw_text)

    classificacao_sugerida = hipoteses[0] if hipoteses else {
        "tipo": "indefinido",
        "confianca": 0.0,
        "racional": "Sem sinais suficientes para sugestão automática.",
    }

    tem_ti_valido = bool(ti_results) and any(
        "[AVISO]" not in v and "[ERRO]" not in v for v in ti_results.values()
    )

    return {
        "resumo_factual": {
            "o_que": o_que,
            "quem": [fields.get("Usuario", "N/A")],
            "onde": [
                v for v in [fields.get("IP_Origem"), fields.get("Destino")]
                if v and str(v).strip().upper() not in {"N/A", "NONE", "NULL", ""}
            ],
            "quando": fields.get("Horario", "N/A"),
            "artefatos": artefatos,
        },
        "hipoteses": hipoteses,
        "lacunas": lacunas,
        "classificacao_sugerida": classificacao_sugerida,
        "mitre_candidato": mitre,
        "modelo_sugerido": "",
        "blocos_recomendados": {
            "incluir_analise_ip": tem_ti_valido,
            "incluir_referencia_mitre": bool(mitre.get("tecnica")),
        },
        "proximos_passos": proximos,
        "alertas_de_qualidade": alertas,
    }
