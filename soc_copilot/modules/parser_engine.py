"""
parser_engine.py
Extração determinística de entidades, normalização de chaves,
classificação de IOCs internos/externos, defang e conversão de timezone.
"""
from __future__ import annotations

from collections import Counter
import ipaddress
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

try:
    import pytz
except ModuleNotFoundError:  # pragma: no cover - fallback para ambientes sem pytz
    pytz = None

# ---------------------------------------------------------------------------
# Mapeamento de chaves do payload para campos normalizados
# ---------------------------------------------------------------------------
KEY_MAP = {
    "Horario": [
        "CreationTime", "StartTime", "LogTime",
        "time",       # FortiGate: campo time (09:25:05, hora local) — antes de EventTime/epoch
        "Timestamp", "timestamp", "datetime", "Time",
        "EventTime",  # FortiGate eventtime = nanosecond epoch — deixar por último
        "date",       # FortiGate: fallback para data
    ],
    "Usuario": [
        "UserId", "Username", "User", "UserName", "user", "AccountName",
        "SamAccountName", "InitiatingUserName", "SourceUser", "usrName",
        "TargetUserName", "NetworkAccountName",
        "srcuser",  # FortiGate
    ],
    "IP_Origem": [
        "ClientIP", "SourceIP", "SourceIp", "src_ip", "sourceip",
        "CallerIpAddress", "IpAddress", "RemoteIP", "src", "Source IP",
        "srcip",    # FortiGate
    ],
    "Destino": [
        "DestinationIp", "DestinationIP", "dst_ip", "ObjectId",
        "Destination", "TargetIP", "RequestURL",
        "Destination IP", "HostUrl",
        "dstip",    # FortiGate (IP destino real — prioridade sobre URL/hostname)
        "hostname", # FortiGate (hostname HTTP do alvo)
        "URL", "url", "dst",
    ],
    "Caminho": [
        "FilePath", "Directory", "Path", "ObjectName",
        "TargetObject", "CommandLine", "File Name", "FolderPath",
        "url",      # FortiGate IPS: URL acessada pelo atacante
    ],
    "LogSource": [
        "LogSource", "Workload", "Category", "source", "DeviceName",
        "ComputerName", "Log Source",
        "devname",  # FortiGate: nome do dispositivo (mais específico que hostname)
        "hostname",
    ],
    "Assunto": [
        "ItemName", "Subject", "FileName", "ProcessName",
        "TaskName", "RuleName", "title", "Event Name",
        "attack",   # FortiGate IPS: nome do ataque detectado
        "msg",      # FortiGate: mensagem resumida da assinatura
    ],
    "Acao": [
        "action",       # FortiGate: dropped, blocked, pass, reset
        "Action", "EventAction", "ActionType",
    ],
    "Protocolo": [
        "proto", "protocol", "Protocol",
    ],
    "Porta_Destino": [
        "dstport", "DestinationPort", "destinationport", "PortaDestino",
    ],
}

_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")
_TS_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2}:\d{2})")
_ISO_TS_WITH_OFFSET_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\b"
)
_IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_SYSLOG_HEADER_RE = re.compile(
    r"^<\d+>\d+\s+\S+\s+(?P<host>\S+)\s+(?P<service>[A-Za-z0-9_.-]+)\s+\d+\s+-\s+-\s+",
    re.MULTILINE,
)
_SNORT_ALERT_RE = re.compile(
    r"\[(?P<gid>\d+):(?P<sid>\d+):(?P<rev>\d+)\]\s+(?P<signature>.+?)\s+\[Classification:\s*(?P<classification>[^\]]+)\]",
    re.IGNORECASE,
)
_SNORT_FLOW_RE = re.compile(
    r"\{(?P<proto>[A-Z]+)\}\s+(?P<src>(?:\d{1,3}\.){3}\d{1,3}):(?P<src_port>\d+)\s+->\s+(?P<dst>(?:\d{1,3}\.){3}\d{1,3}):(?P<dst_port>\d+)",
    re.IGNORECASE,
)
_FILTERLOG_FLOW_RE = re.compile(
    r",(?P<proto>tcp|udp|icmp),\d+,(?P<src>(?:\d{1,3}\.){3}\d{1,3}),(?P<dst>(?:\d{1,3}\.){3}\d{1,3}),(?P<src_port>\d+),(?P<dst_port>\d+),",
    re.IGNORECASE,
)
_FILTERLOG_ACTION_RE = re.compile(
    r"filterlog\s+\d+\s+-\s+-\s+[^,\r\n]*,(?:[^,\r\n]*,){5}(?P<action>pass|block|blocked|deny|denied|drop|dropped|reject|rejected|match)",
    re.IGNORECASE,
)
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

# URLs de referência de vendor — campo `ref=` do FortiGate e similares
# Não são destino real do ataque, são links para a base de conhecimento da assinatura
_VENDOR_REF_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:fortinet\.com/ids|snort\.org/rule-docs|"
    r"emergingthreats\.net|attack\.mitre\.org|cve\.mitre\.org|"
    r"nvd\.nist\.gov|docs\.microsoft\.com/security|"
    r"technet\.microsoft\.com)",
    re.IGNORECASE,
)


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

try:
    _SP = pytz.timezone("America/Sao_Paulo") if pytz else ZoneInfo("America/Sao_Paulo")
except Exception:  # pragma: no cover - fallback para runtimes sem base tz instalada
    _SP = timezone(timedelta(hours=-3))


def _localize_utc(dt: datetime) -> datetime:
    if pytz:
        return pytz.utc.localize(dt)
    return dt.replace(tzinfo=timezone.utc)


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

    text = time_str.strip()

    # Timestamps ISO com offset explícito já carregam timezone real do evento.
    if re.search(r"(Z|[+-]\d{2}:\d{2})$", text):
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return dt.astimezone(_SP).strftime("%H:%M:%S")
        except ValueError:
            pass

    # Tentativa 1: padrão ISO (YYYY-MM-DD HH:MM:SS)
    match = _TS_PATTERN.search(time_str)
    if match:
        try:
            dt_utc = _localize_utc(
                datetime.strptime(f"{match.group(1)} {match.group(2)}", "%Y-%m-%d %H:%M:%S")
            )
            return dt_utc.astimezone(_SP).strftime("%H:%M:%S")
        except Exception:
            pass

    # Tentativa 2: formatos adicionais (locale US, ISO com Z, BR)
    for fmt, converte in _EXTRA_TS_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            if converte:
                dt = _localize_utc(dt).astimezone(_SP)
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

    urls = sorted(
        u for u in set(_URL_PATTERN.findall(text or ""))
        if not _VENDOR_REF_URL_RE.match(u)
    )
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
            re.compile(r"(?i)\bsrcip=((?:\d{1,3}\.){3}\d{1,3})"),                      # FortiGate
            re.compile(r"(?i)\b(?:source ip|sourceip|src_ip|src|clientip|ip de origem)\s*[:=]\s*((?:\d{1,3}\.){3}\d{1,3})"),
        ],
        "destino": [
            re.compile(r"(?i)\bdstip=((?:\d{1,3}\.){3}\d{1,3})"),                       # FortiGate
            re.compile(r"(?i)\b(?:destination ip|destinationip|dst_ip|dst|targetip|destino)\s*[:=]\s*((?:\d{1,3}\.){3}\d{1,3})"),
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


def _fallback_log_source(raw_text: str) -> str:
    match = _SYSLOG_HEADER_RE.search(raw_text or "")
    if not match:
        return "N/A"
    service = _sanitize_value(match.group("service"))
    host = _sanitize_value(match.group("host"))
    if service != "N/A" and host != "N/A":
        return f"{service} @ {host}"
    return service if service != "N/A" else host


def _fallback_assunto(raw_text: str) -> str:
    text = raw_text or ""
    snort = _SNORT_ALERT_RE.search(text)
    if snort:
        signature = _sanitize_value(snort.group("signature"))
        classification = _sanitize_value(snort.group("classification"))
        if signature != "N/A" and classification != "N/A":
            return f"{signature} - {classification}"
        return signature

    patterns = [
        re.compile(r"(?i)\b(?:attack|signature|alert|msg|rule name|rulename)\s*[:=]\s*([^\r\n|]+)"),
        re.compile(r"(?i)\b(?:tcp[_\s-]?port[_\s-]?scan|udp[_\s-]?scan|port[_\s-]?scan|ping sweep|dns ptr scan)\b"),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            value = match.group(1) if match.groups() else match.group(0)
            return _sanitize_value(value)
    return "N/A"


def _fallback_action(raw_text: str) -> str:
    text = raw_text or ""
    filterlog = _FILTERLOG_ACTION_RE.search(text)
    if filterlog:
        action = filterlog.group("action")
        if action and action.lower() != "match":
            return action

    generic = re.search(
        r"(?i)\b(pass|allow|allowed|block|blocked|deny|denied|drop|dropped|reset|reject|rejected)\b",
        text,
    )
    if generic:
        return generic.group(1)
    return "N/A"


def _fallback_protocol_and_port(raw_text: str) -> tuple[str, str]:
    text = raw_text or ""
    snort = _SNORT_FLOW_RE.search(text)
    if snort:
        return snort.group("proto").lower(), snort.group("dst_port")

    filterlog = _FILTERLOG_FLOW_RE.search(text)
    if filterlog:
        return filterlog.group("proto").lower(), filterlog.group("dst_port")

    generic = re.search(
        r"(?i)\b(tcp|udp|icmp)\b.*?\b(?:dstport|porta destino|destination port)\s*[:=]?\s*(\d{1,5})",
        text,
    )
    if generic:
        return generic.group(1).lower(), generic.group(2)
    return "N/A", "N/A"


def _parse_filterlog_event(line: str) -> dict | None:
    if "filterlog" not in (line or "") or " - - " not in line:
        return None

    header, payload = line.split(" - - ", 1)
    tokens = header.split()
    if len(tokens) < 4 or tokens[3].lower() != "filterlog":
        return None

    columns = payload.split(",")
    if len(columns) < 22:
        return None

    proto = _sanitize_value(columns[16]).lower()
    src = _sanitize_value(columns[18])
    dst = _sanitize_value(columns[19])
    src_port = _sanitize_value(columns[20])
    dst_port = _sanitize_value(columns[21])

    if proto not in {"tcp", "udp", "icmp"}:
        return None

    try:
        ipaddress.ip_address(src)
        ipaddress.ip_address(dst)
    except ValueError:
        return None

    try:
        timestamp = datetime.fromisoformat(tokens[1].replace("Z", "+00:00")).astimezone(_SP)
    except ValueError:
        timestamp = None

    return {
        "timestamp": timestamp,
        "action": _sanitize_value(columns[6]).lower(),
        "direction": _sanitize_value(columns[7]).lower(),
        "proto": proto,
        "src": src,
        "dst": dst,
        "src_port": src_port,
        "dst_port": dst_port,
    }


def _format_duration_pt(seconds: int) -> str:
    seconds = max(int(seconds), 0)
    horas, resto = divmod(seconds, 3600)
    minutos, segundos = divmod(resto, 60)

    partes: list[str] = []
    if horas:
        partes.append(f"{horas} hora{'s' if horas != 1 else ''}")
    if minutos:
        partes.append(f"{minutos} minuto{'s' if minutos != 1 else ''}")
    if segundos and not horas:
        partes.append(f"{segundos} segundo{'s' if segundos != 1 else ''}")
    if not partes:
        return "0 segundos"
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + f" e {partes[-1]}"


def _format_window_pt(start: datetime | None, end: datetime | None) -> tuple[str, str]:
    if not start or not end:
        return "", ""
    seconds = int((end - start).total_seconds())
    return _format_duration_pt(seconds), f"entre {start.strftime('%H:%M:%S')} e {end.strftime('%H:%M:%S')}"


def _format_top_ports(events: list[dict], limit: int = 2) -> str:
    counts = Counter(
        (event["proto"].upper(), event["dst_port"])
        for event in events
        if event.get("dst_port", "").isdigit()
    )
    if not counts:
        return ""

    partes: list[str] = []
    for (proto, port), total in counts.most_common(limit):
        partes.append(f"{proto}/{port} ({total} evento{'s' if total != 1 else ''})")
    return ", ".join(partes)


def _summarize_horizontal_scan(src: str, events: list[dict]) -> dict[str, str] | None:
    unique_targets = {event["dst"] for event in events}
    if len(unique_targets) < 10:
        return None

    timestamps = [event["timestamp"] for event in events if event.get("timestamp")]
    start = min(timestamps) if timestamps else None
    end = max(timestamps) if timestamps else None
    duracao, janela = _format_window_pt(start, end)
    portas = _format_top_ports(events)
    metadata_hits = sum(1 for event in events if event["dst"] == "169.254.169.254")
    dominant_proto = Counter(event["proto"] for event in events).most_common(1)[0][0]

    frases = [
        (
            f"O host {src} apresentou comportamento compatível com reconhecimento de rede, "
            f"alcançando {len(unique_targets)} endereços de IP de destino únicos"
            + (f" em uma janela de {duracao} ({janela})" if duracao and janela else "")
            + "."
        )
    ]
    if portas:
        frases.append(f"Houve predominância de conexões nas portas {portas}.")
    if metadata_hits:
        frases.append(
            f"Também foram observadas {metadata_hits} tentativa{'s' if metadata_hits != 1 else ''} "
            "de acesso ao endereço de metadados 169.254.169.254."
        )

    assunto = {
        "icmp": "Ping Sweep",
        "udp": "UDP Port Scan",
        "tcp": "TCP Port Scan",
    }.get(dominant_proto, "Network Scan")

    return {
        "resumo": " ".join(frases),
        "assunto": assunto,
        "fonte_principal": src,
        "janela": janela,
        "alvos_unicos": str(len(unique_targets)),
        "tipo": "horizontal",
    }


def _summarize_vertical_scan(src: str, dst: str, events: list[dict]) -> dict[str, str] | None:
    ports = sorted({int(event["dst_port"]) for event in events if event.get("dst_port", "").isdigit()})
    if len(ports) < 10:
        return None

    timestamps = [event["timestamp"] for event in events if event.get("timestamp")]
    start = min(timestamps) if timestamps else None
    end = max(timestamps) if timestamps else None
    duracao, janela = _format_window_pt(start, end)
    dominant_proto = Counter(event["proto"] for event in events).most_common(1)[0][0].upper()
    action_counts = Counter(event["action"] for event in events if event.get("action"))
    blocked_events = sum(
        total for action, total in action_counts.items()
        if action in {"block", "blocked", "deny", "denied", "drop", "dropped", "reject", "rejected"}
    )

    prefixo = (
        f"Foram registrados {blocked_events} evento{'s' if blocked_events != 1 else ''} de bloqueio "
        if blocked_events
        else f"Foram registrados {len(events)} evento{'s' if len(events) != 1 else ''} "
    )
    intervalo = f"({ports[0]} a {ports[-1]})" if ports else ""
    faixa_texto = "em sequência" if len(ports) == (ports[-1] - ports[0] + 1) else "no intervalo"

    frase = (
        f"{prefixo}em sondagens {dominant_proto} originadas de {src} contra {dst}, "
        f"cobrindo {len(ports)} porta{'s' if len(ports) != 1 else ''} de destino {faixa_texto} {intervalo}"
        + (f" em uma janela de {duracao} ({janela})" if duracao and janela else "")
        + "."
    )

    assunto = f"{dominant_proto} Port Scan"
    return {
        "resumo": frase,
        "assunto": assunto,
        "fonte_principal": src,
        "alvo_principal": dst,
        "janela": janela,
        "portas_unicas": str(len(ports)),
        "tipo": "vertical",
    }


def _build_scan_summary(raw_text: str) -> dict[str, str]:
    events = [
        event for line in (raw_text or "").splitlines()
        if (event := _parse_filterlog_event(line))
    ]
    if len(events) < 10:
        return {}

    source_groups: dict[str, list[dict]] = {}
    pair_groups: dict[tuple[str, str], list[dict]] = {}
    for event in events:
        source_groups.setdefault(event["src"], []).append(event)
        pair_groups.setdefault((event["src"], event["dst"]), []).append(event)

    horizontal_candidates = [
        _summarize_horizontal_scan(src, source_events)
        for src, source_events in source_groups.items()
    ]
    horizontal_candidates = [candidate for candidate in horizontal_candidates if candidate]
    horizontal_candidates.sort(
        key=lambda item: (
            int(item.get("alvos_unicos", "0")),
            item.get("fonte_principal", ""),
        ),
        reverse=True,
    )

    vertical_candidates = [
        _summarize_vertical_scan(src, dst, pair_events)
        for (src, dst), pair_events in pair_groups.items()
    ]
    vertical_candidates = [candidate for candidate in vertical_candidates if candidate]
    vertical_candidates.sort(
        key=lambda item: (
            int(item.get("portas_unicas", "0")),
            item.get("fonte_principal", ""),
        ),
        reverse=True,
    )

    if not horizontal_candidates and not vertical_candidates:
        return {}

    principal = horizontal_candidates[0] if horizontal_candidates else vertical_candidates[0]
    resumos = [principal["resumo"]]

    if vertical_candidates:
        vertical = vertical_candidates[0]
        if vertical is not principal:
            resumos.append(vertical["resumo"])

    return {
        "resumo": " ".join(part for part in resumos if part),
        "assunto": principal.get("assunto", ""),
        "fonte_principal": principal.get("fonte_principal", ""),
        "alvo_principal": principal.get("alvo_principal", ""),
        "tipo": "+".join(
            tipo for tipo in [
                horizontal_candidates[0]["tipo"] if horizontal_candidates else "",
                vertical_candidates[0]["tipo"] if vertical_candidates else "",
            ] if tipo
        ),
    }


def parse(raw_fields: dict, raw_text: str) -> dict:
    """
    Recebe os campos brutos e o texto original.
    Retorna campos normalizados prontos para o draft_engine.
    """
    horario_raw = _resolve_field(raw_fields, KEY_MAP["Horario"])
    usuario = _resolve_field(raw_fields, KEY_MAP["Usuario"])
    ip_origem = _resolve_field(raw_fields, KEY_MAP["IP_Origem"])
    destino = _resolve_field(raw_fields, KEY_MAP["Destino"])
    destino_raw = destino
    caminho = _resolve_field(raw_fields, KEY_MAP["Caminho"])
    log_source = _resolve_field(raw_fields, KEY_MAP["LogSource"])
    assunto = _resolve_field(raw_fields, KEY_MAP["Assunto"])
    acao = _resolve_field(raw_fields, KEY_MAP["Acao"])
    protocolo = _resolve_field(raw_fields, KEY_MAP["Protocolo"])
    porta_destino = _resolve_field(raw_fields, KEY_MAP["Porta_Destino"])

    iocs = extract_iocs(raw_text)
    scan_summary = _build_scan_summary(raw_text)

    if horario_raw == "N/A":
        iso_match = _ISO_TS_WITH_OFFSET_RE.search(raw_text or "")
        horario_raw = iso_match.group(0) if iso_match else _search_in_text(_TS_PATTERN, raw_text)
    horario = convert_to_sp(horario_raw)

    if usuario == "N/A":
        usuario = _fallback_usuario(raw_text)

    if ip_origem == "N/A":
        ip_origem = _fallback_ip(raw_text, "origem")
    if ip_origem == "N/A" and len(iocs["ips_externos"]) == 1:
        ip_origem = iocs["ips_externos"][0]
    elif ip_origem == "N/A" and len(iocs["ips_internos"]) == 1:
        ip_origem = iocs["ips_internos"][0]
    if ip_origem == "N/A" and scan_summary.get("fonte_principal"):
        ip_origem = scan_summary["fonte_principal"]

    if destino == "N/A":
        destino = _fallback_destino(raw_text, iocs)
    if scan_summary.get("tipo") == "vertical" and destino_raw == "N/A" and scan_summary.get("alvo_principal"):
        destino = scan_summary["alvo_principal"]
    elif "horizontal" in scan_summary.get("tipo", "") and destino_raw == "N/A":
        destino = "N/A"

    if log_source == "N/A":
        log_source = _fallback_log_source(raw_text)

    if assunto == "N/A":
        assunto = _fallback_assunto(raw_text)
    if assunto == "N/A" and scan_summary.get("assunto"):
        assunto = scan_summary["assunto"]

    if acao == "N/A":
        acao = _fallback_action(raw_text)

    if protocolo == "N/A" or porta_destino == "N/A":
        proto_fallback, dst_port_fallback = _fallback_protocol_and_port(raw_text)
        if protocolo == "N/A":
            protocolo = proto_fallback
        if porta_destino == "N/A":
            porta_destino = dst_port_fallback

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
        "Acao": acao,
        "Protocolo": protocolo,
        "Porta_Destino": porta_destino,
        "IOCs": iocs,
        "Resumo_Scan": scan_summary.get("resumo", "N/A"),
        "Tipo_Scan": scan_summary.get("tipo", "N/A"),
    }
