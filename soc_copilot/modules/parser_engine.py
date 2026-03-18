"""
parser_engine.py
Extração determinística de entidades, normalização de chaves,
classificação de IOCs internos/externos, defang e conversão de timezone.
"""
from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from urllib.parse import urlparse

import pytz

# ---------------------------------------------------------------------------
# Mapeamento de chaves do payload para campos normalizados
# ---------------------------------------------------------------------------
KEY_MAP = {
    "Horario": [
        "CreationTime", "StartTime", "LogTime", "EventTime",
        "Timestamp", "timestamp", "time", "datetime", "Time",
    ],
    "Usuario": [
        "UserId", "Username", "User", "UserName", "user", "AccountName",
        "SamAccountName", "InitiatingUserName", "SourceUser", "usrName",
        "TargetUserName", "NetworkAccountName",
    ],
    "IP_Origem": [
        "ClientIP", "SourceIP", "SourceIp", "src_ip", "sourceip",
        "CallerIpAddress", "IpAddress", "RemoteIP", "src", "Source IP",
    ],
    "Destino": [
        "DestinationIp", "DestinationIP", "dst_ip", "ObjectId",
        "Destination", "TargetIP", "URL", "url", "RequestURL",
        "Destination IP", "dst", "HostUrl",
    ],
    "Caminho": [
        "FilePath", "Directory", "Path", "ObjectName",
        "TargetObject", "CommandLine", "File Name", "FolderPath",
    ],
    "LogSource": [
        "LogSource", "Workload", "Category", "source", "DeviceName",
        "ComputerName", "hostname", "Log Source",
    ],
    "Assunto": [
        "ItemName", "Subject", "FileName", "ProcessName",
        "TaskName", "RuleName", "title", "Event Name",
    ],
}

_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")
_TS_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2}:\d{2})")
_IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_DOMAIN_PATTERN = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,63})\b",
    re.IGNORECASE,
)
# TLDs reconhecidos como válidos para extração de IOCs.
# TLDs que parecem palavras comuns em inglês/português (Published, Outlook, Local, etc.)
# são excluídos para evitar que nomes de produto virem domínios falsos.
_VALID_TLDS = {
    "ac","ad","ae","af","ag","ai","al","am","ao","aq","ar","as","at","au",
    "aw","az","ba","bb","bd","be","bf","bg","bh","bi","bj","bm","bn","bo",
    "br","bs","bt","bw","by","bz","ca","cc","cd","cf","cg","ch","ci","ck",
    "cl","cm","cn","co","cr","cu","cv","cx","cy","cz","de","dj","dk","dm",
    "do","dz","ec","ee","eg","er","es","et","eu","fi","fj","fk","fm","fo",
    "fr","ga","gd","ge","gf","gg","gh","gi","gl","gm","gn","gp","gq","gr",
    "gs","gt","gu","gw","gy","hk","hm","hn","hr","ht","hu","id","ie","il",
    "im","in","io","iq","ir","is","it","je","jm","jo","jp","ke","kg","kh",
    "ki","km","kn","kp","kr","kw","ky","kz","la","lb","lc","li","lk","lr",
    "ls","lt","lu","lv","ly","ma","mc","md","me","mg","mh","mk","ml","mn",
    "mo","mp","mq","mr","ms","mt","mu","mv","mw","mx","my","mz","na","nc",
    "ne","nf","ng","ni","nl","no","np","nr","nu","nz","om","pa","pe","pf",
    "pg","ph","pk","pl","pm","pn","pr","ps","pt","pw","py","qa","re","ro",
    "rs","ru","rw","sa","sb","sc","sd","se","sg","sh","si","sk","sl","sm",
    "sn","so","sr","ss","st","su","sv","sx","sy","sz","tc","td","tf","tg",
    "th","tj","tk","tl","tm","tn","to","tr","tt","tv","tw","tz","ua","ug",
    "uk","us","uy","uz","va","vc","ve","vg","vi","vn","vu","wf","ws","ye",
    "yt","za","zm","zw",
    # gTLDs comuns
    "com","net","org","gov","edu","mil","int","biz","info","name","pro",
    "aero","coop","museum","mobi","tel","travel","jobs","post",
    # Novos gTLDs frequentes em contexto corporativo/segurança
    "app","dev","io","ai","cloud","online","site","tech","digital","security",
    "media","store","shop","blog","news","live","web","agency","finance",
    "bank","insurance","health","legal","services","solutions","systems",
    "network","software","email","mail","support","help","local",
}

# Domínios de infraestrutura conhecida que não são IOCs de ameaça
_INFRA_DOMAIN_SUFFIXES = {
    "microsoft.com", "office365.com", "outlook.com", "windows.net",
    "live.com", "hotmail.com", "azure.com", "cloudapp.net", "office.com",
    "protection.outlook.com", "sharepoint.com", "onedrive.com",
    "googleapis.com", "google.com", "googleusercontent.com", "gstatic.com",
    "amazon.com", "amazonaws.com", "cloudfront.net", "awsdns-1.com",
    "akamaitechnologies.com", "akamaiedge.net", "fastly.net",
}


def _is_valid_domain_ioc(domain: str) -> bool:
    """Retorna True se o domínio tem aparência de IOC real (não produto/infra)."""
    lower = domain.lower()
    # Filtra domínios de infraestrutura conhecida
    for suffix in _INFRA_DOMAIN_SUFFIXES:
        if lower == suffix or lower.endswith("." + suffix):
            return False
    # Valida TLD contra lista de TLDs reconhecidos
    parts = lower.rsplit(".", 1)
    if len(parts) < 2:
        return False
    tld = parts[-1]
    return tld in _VALID_TLDS


_HASH_PATTERNS = [
    re.compile(r"\b[a-fA-F0-9]{64}\b"),
    re.compile(r"\b[a-fA-F0-9]{40}\b"),
    re.compile(r"\b[a-fA-F0-9]{32}\b"),
]

_SP = pytz.timezone("America/Sao_Paulo")


def _sanitize_value(value) -> str:
    if value is None:
        return "N/A"
    text = str(value).strip()
    return text if text and text.lower() not in ("none", "null", "nan") else "N/A"


def _normalize_key(key: str) -> str:
    return re.sub(r"[\s._\-]+", "", key).lower()


def _build_lookup(raw: dict) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for key, value in raw.items():
        if key is None:
            continue
        key_str = str(key).strip()
        if not key_str:
            continue
        lookup[_normalize_key(key_str)] = _sanitize_value(value)
    return lookup


def _is_private_ip(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_private or ipaddress.ip_address(ip).is_loopback or ipaddress.ip_address(ip).is_link_local
    except ValueError:
        return False


def _resolve_field(raw: dict, candidates: list[str], default: str = "N/A") -> str:
    lookup = _build_lookup(raw)
    for key in candidates:
        value = lookup.get(_normalize_key(key))
        if value and value != "N/A":
            return value
    return default


def _search_in_text(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text or "")
    return match.group(0).strip() if match else "N/A"


_EXTRA_TS_FORMATS = [
    # (formato, converte_utc_para_sp)
    ("%b %d, %Y, %I:%M:%S %p",  True),   # Mar 18, 2026, 10:04:30 PM
    ("%b %d, %Y %I:%M:%S %p",   True),   # Mar 18, 2026 10:04:30 PM
    ("%B %d, %Y, %I:%M:%S %p",  True),   # March 18, 2026, 10:04:30 PM
    ("%Y-%m-%dT%H:%M:%S.%fZ",   True),   # 2026-03-18T22:04:30.000Z
    ("%Y-%m-%dT%H:%M:%SZ",      True),   # 2026-03-18T22:04:30Z
    ("%d/%m/%Y %H:%M:%S",       False),  # 18/03/2026 22:04:30 (já em SP)
    ("%m/%d/%Y %I:%M:%S %p",    True),   # 03/18/2026 10:04:30 PM
]


def convert_to_sp(time_str: str) -> str:
    """Converte timestamp UTC para São Paulo. Retorna HH:MM:SS."""
    if not time_str or time_str == "N/A":
        return time_str

    # Tentativa 1: padrão ISO (YYYY-MM-DD HH:MM:SS)
    match = _TS_PATTERN.search(time_str)
    if match:
        try:
            dt_utc = pytz.utc.localize(
                datetime.strptime(f"{match.group(1)} {match.group(2)}", "%Y-%m-%d %H:%M:%S")
            )
            return dt_utc.astimezone(_SP).strftime("%H:%M:%S")
        except Exception:
            pass

    # Tentativa 2: formatos adicionais (locale US, ISO com Z, BR)
    text = time_str.strip()
    for fmt, converte in _EXTRA_TS_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            if converte:
                dt = pytz.utc.localize(dt).astimezone(_SP)
            return dt.strftime("%H:%M:%S")
        except ValueError:
            continue

    # Tentativa 3: extrai HH:MM:SS puro se presente (sem conversão)
    hms = re.search(r"\b(\d{2}:\d{2}:\d{2})\b", time_str)
    if hms:
        return hms.group(1)

    return time_str


def defang(value: str) -> str:
    """Desarma URLs, domínios e IPs quando fizer sentido expô-los no texto."""
    if not value or value == "N/A":
        return value
    if "@" in value:
        return value
    if "." in value:
        return value.replace(".", "[.]")
    return value


def _extract_domains_from_urls(urls: list[str]) -> list[str]:
    domains: set[str] = set()
    for url in urls:
        try:
            parsed = urlparse(url)
            host = parsed.hostname
            if host:
                domains.add(host)
        except Exception:
            continue
    return sorted(domains)


def extract_iocs(text: str) -> dict:
    """
    Retorna IOCs normalizados a partir do texto bruto.
    """
    ips_ext: set[str] = set()
    ips_int: set[str] = set()

    for ip in set(_IP_PATTERN.findall(text or "")):
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            continue
        if _is_private_ip(ip):
            ips_int.add(ip)
        else:
            ips_ext.add(ip)

    urls = sorted(set(_URL_PATTERN.findall(text or "")))
    url_domains = set(_extract_domains_from_urls(urls))

    # Partes locais de e-mails (ex: NO-REPLY.ATENDIMENTO em NO-REPLY.ATENDIMENTO@dominio.com)
    # não são domínios — excluir da extração para evitar falsos positivos
    email_local_parts: set[str] = {
        m.group(1).lower()
        for m in re.finditer(r"\b([\w.\-+]+)@[\w.\-]+\.[a-zA-Z]{2,}\b", text or "")
    }

    raw_domains = {
        d for d in _DOMAIN_PATTERN.findall(text or "")
        if d not in url_domains
        and not d.replace(".", "").isdigit()
        and d.lower() not in email_local_parts
        and _is_valid_domain_ioc(d)
    }
    hashes: set[str] = set()
    for pattern in _HASH_PATTERNS:
        hashes.update(pattern.findall(text or ""))

    return {
        "ips_externos": sorted(ips_ext),
        "ips_internos": sorted(ips_int),
        "urls": urls,
        "dominios": sorted(raw_domains),
        "hashes": sorted(hashes),
    }


def _fallback_usuario(raw_text: str) -> str:
    email = _search_in_text(_EMAIL_RE, raw_text)
    if email != "N/A":
        return email

    patterns = [
        re.compile(r"(?i)\b(?:usu[aá]rio|user|username|account ?name)\s*[:=]\s*([^\r\n|,;]+)"),
        re.compile(r"(?i)\b(?:SourceUser|TargetUserName|usrName)\s*[:=]\s*([^\r\n|,;]+)"),
    ]
    for pattern in patterns:
        match = pattern.search(raw_text or "")
        if match:
            return _sanitize_value(match.group(1))
    return "N/A"


def _fallback_ip(raw_text: str, kind: str) -> str:
    label_map = {
        "origem": [
            re.compile(r"(?i)\b(?:source ip|sourceip|src|clientip|ip de origem)\s*[:=]\s*((?:\d{1,3}\.){3}\d{1,3})"),
        ],
        "destino": [
            re.compile(r"(?i)\b(?:destination ip|destinationip|dst|targetip|destino)\s*[:=]\s*((?:\d{1,3}\.){3}\d{1,3})"),
        ],
    }
    for pattern in label_map[kind]:
        match = pattern.search(raw_text or "")
        if match:
            return match.group(1)
    return "N/A"


def _fallback_destino(raw_text: str, iocs: dict) -> str:
    dest_ip = _fallback_ip(raw_text, "destino")
    if dest_ip != "N/A":
        return dest_ip
    if iocs["urls"]:
        return defang(iocs["urls"][0])
    if iocs["dominios"]:
        return defang(iocs["dominios"][0])
    if iocs["ips_externos"]:
        return iocs["ips_externos"][0]
    return "N/A"


def parse(raw_fields: dict, raw_text: str) -> dict:
    """
    Recebe os campos brutos e o texto original.
    Retorna campos normalizados prontos para o draft_engine.
    """
    horario_raw = _resolve_field(raw_fields, KEY_MAP["Horario"])
    usuario = _resolve_field(raw_fields, KEY_MAP["Usuario"])
    ip_origem = _resolve_field(raw_fields, KEY_MAP["IP_Origem"])
    destino = _resolve_field(raw_fields, KEY_MAP["Destino"])
    caminho = _resolve_field(raw_fields, KEY_MAP["Caminho"])
    log_source = _resolve_field(raw_fields, KEY_MAP["LogSource"])
    assunto = _resolve_field(raw_fields, KEY_MAP["Assunto"])

    iocs = extract_iocs(raw_text)

    if horario_raw == "N/A":
        horario_raw = _search_in_text(_TS_PATTERN, raw_text)
    horario = convert_to_sp(horario_raw)

    if usuario == "N/A":
        usuario = _fallback_usuario(raw_text)

    if ip_origem == "N/A":
        ip_origem = _fallback_ip(raw_text, "origem")
    if ip_origem == "N/A" and len(iocs["ips_externos"]) == 1:
        ip_origem = iocs["ips_externos"][0]
    elif ip_origem == "N/A" and len(iocs["ips_internos"]) == 1:
        ip_origem = iocs["ips_internos"][0]

    if destino == "N/A":
        destino = _fallback_destino(raw_text, iocs)

    # Defang apenas quando for URL ou domínio — IPs estruturados não são defangeados
    if destino != "N/A" and "http" in destino.lower():
        destino = defang(destino)
    elif destino != "N/A" and "." in destino:
        try:
            ipaddress.ip_address(destino)  # É um IP — não defangar
        except ValueError:
            destino = defang(destino)  # É domínio/URL — defangar

    return {
        "Horario": horario,
        "Usuario": usuario,
        "IP_Origem": ip_origem,
        "IP_Origem_Privado": _is_private_ip(ip_origem) if ip_origem != "N/A" else True,
        "Destino": destino,
        "Caminho": caminho,
        "LogSource": log_source,
        "Assunto": assunto,
        "IOCs": iocs,
    }
