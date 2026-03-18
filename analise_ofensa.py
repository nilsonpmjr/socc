import json
import csv
import re
import sys
import subprocess
from datetime import datetime
import argparse
import os

try:
    import pytz
except ImportError:
    print("Módulo 'pytz' não encontrado. Por favor, instale: pip install pytz")
    sys.exit(1)

def convert_time_to_sp(time_str):
    """
    Converte um timestamp genérico (normalmente UTC no QRadar) para o fuso de São Paulo.
    Retorna no formato exigido pelo SOP: HH:MM:SS
    """
    try:
        # Regex para capturar data e hora (ex: 2026-03-18T11:36:00)
        match = re.search(r'(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2}:\d{2})', time_str)
        if not match:
            return time_str
        
        datetime_str = f"{match.group(1)} {match.group(2)}"
        dt_utc = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
        dt_utc = pytz.utc.localize(dt_utc)
        
        sp_tz = pytz.timezone('America/Sao_Paulo')
        dt_sp = dt_utc.astimezone(sp_tz)
        return dt_sp.strftime("%H:%M:%S")
    except Exception:
        return time_str

def defang_url(url):
    """ Desarma URLs e pontuações de domínios (ex: google.com -> google[.]com) """
    if not url or url == 'N/A':
        return url
    return url.replace('.', '[.]')

def run_threat_intel(ioc):
    """ Aciona o checker existente para IP/Domínio/Hash """
    script_path = r"C:\Users\Nilson.Miranda\Threat-Intelligence-Tool\backend\threat_check.py"
    if not os.path.exists(script_path):
        return "Ferramenta de Threat Intel não encontrada no caminho padrão."
        
    try:
        print(f"[*] Consultando TI para o IOC: {ioc} ...")
        result = subprocess.run(
            ["python", script_path, "--dashboard", ioc], 
            capture_output=True, text=True, timeout=30
        )
        return result.stdout.strip()
    except Exception as e:
        return f"Falha ao consultar {ioc}: {e}"

def extract_iocs(text):
    """ Extrai IPs públicos ignorando privados comuns e bogons """
    ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
    ips = re.findall(ip_pattern, text)
    public_ips = []
    
    for ip in ips:
        parts = ip.split('.')
        if len(parts) == 4:
            if parts[0] == '10' or (parts[0] == '172' and 16 <= int(parts[1]) <= 31) or (parts[0] == '192' and parts[1] == '168') or parts[0] in ['127', '0']:
                continue
            public_ips.append(ip)
    return list(set(public_ips))

def process_payload(file_path):
    """ Processa o Payload e extrai valores chaves baseados no padrão JSON do QRadar e O365 """
    data = {}
    content = ""
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            data = json.loads(content)
    except Exception:
        # Tenta Parse flexível
        pass

    # Campos padronizados para a resposta
    fields = {
        "Horario": "N/A",
        "Usuario": "N/A",
        "IP_Origem": "N/A",
        "Destino": "N/A",
        "Caminho": "N/A",
        "LogSource": "N/A",
        "Assunto": "N/A",
        "IOCs": []
    }

    if isinstance(data, dict):
        # Tenta extrair dados padronizados
        fields["Horario"] = data.get("CreationTime", data.get("StartTime", data.get("LogTime", "N/A")))
        fields["Usuario"] = data.get("UserId", data.get("Username", data.get("User", "N/A")))
        fields["IP_Origem"] = data.get("ClientIP", data.get("SourceIP", data.get("SourceIp", "N/A")))
        fields["Destino"] = data.get("DestinationIp", data.get("ObjectId", data.get("Destination", "N/A")))
        fields["Caminho"] = data.get("FilePath", data.get("Directory", "N/A"))
        fields["LogSource"] = data.get("LogSource", data.get("Workload", "N/A"))
        fields["Assunto"] = data.get("ItemName", data.get("Subject", "N/A"))

    # Converte fuso para São Paulo
    if fields["Horario"] != "N/A":
        fields["Horario"] = convert_time_to_sp(fields["Horario"])
        
    # Desarma URLs e Destinos
    if isinstance(fields["Destino"], str):
        fields["Destino"] = defang_url(fields["Destino"])
    if isinstance(fields["Usuario"], str):
        fields["Usuario"] = defang_url(fields["Usuario"])

    # Extrai IOCs de rede no texto bruto (para análise)
    fields["IOCs"] = extract_iocs(content)
    
    # Se IP de origem não foi pego no JSON mas tem 1 IOC de rede publico e unico, assume ele
    if fields["IP_Origem"] == "N/A" and len(fields["IOCs"]) == 1:
        fields["IP_Origem"] = fields["IOCs"][0]

    return fields

def generate_drafts(fields, intel_results):
    """ Gera os modelos rascunhados (TP, BTP, FP) com base nas regras do SOP """
    
    tp_template = f"""========================= [ TRUE POSITIVE (ALERTA COMPLET0) ] =========================
Prezados,

[Insira um Título Descritivo e Claro Aqui]

O evento iniciou às {fields['Horario']}, partindo da conta/IP "{fields['IP_Origem']}" (ou "{fields['Usuario']}") em direção a "{fields['Destino']}". Ocorreu [Descreva a ação técnica, ex: acesso não autorizado ou execução de comando].

Usuário: {fields['Usuario']}

IP de Origem: {fields['IP_Origem']}

Destino: {fields['Destino']}

Diretório/Caminho: {fields['Caminho']}

Log Source: {fields['LogSource']}"""

    if intel_results:
        tp_template += f"\n\nAnálise do IP:\n{intel_results}"
        
    tp_template += """\n\nAnálise Técnica: [Descreva objetivamente o motivo do alerta. Ex: Atividade identificada como maliciosa com base no payload evadindo controles.]

Em anexo o Payload.

Referência: [Insira o texto descritivo do MITRE]

Referência MITRE: [Insira o link MITRE]

Recomendamos [Isolar o ativo impactado, forçar o encerramento da sessão do usuário envolvido e redefinir credenciais].
========================================================================================="""

    btp_template = f"""========================= [ BENIGN TRUE POSITIVE (ENCERRAMENTO) ] =========================
Classificação Final: Benign True Positive

Resumo Técnico: O evento envolvendo o usuário {fields['Usuario']} com a origem {fields['IP_Origem']} foi corretamente disparado pela regra devido ao comportamento previsto no sistema.

Justificativa da benignidade: [Preencha com o motivo. Ex: Tratava-se de uma intervenção administrativa justificada (GMUD X) ou ferramenta de scanner interna conhecida.]

Ação de encerramento: O caso está sendo encerrado sem impacto identificado e o cliente ciente (se aplicável).
==========================================================================================="""

    fp_template = f"""========================= [ FALSE POSITIVE / TRUE NEGATIVE (ENCERRAMENTO) ] =========================
Classificação Final: False Positive / True Negative

Justificativa: As evidências extraídas (Usuário: {fields['Usuario']}, Origem: {fields['IP_Origem']}) não sustentam a caracterização de um incidente de segurança. O contexto indica [Preencha: erro de log, regra inadequada, comportamento padrão inocente].

Ação recomendada: Avaliar ajuste (Tuning) na regra se a volumetria for alta. Reclassificação da ofensa.
====================================================================================================="""

    return tp_template, btp_template, fp_template

def main():
    parser = argparse.ArgumentParser(description='Automacao SOC: Analise de Payload e geracao de notas (SOP)')
    parser.add_argument('file', help='Caminho para o arquivo Payload (JSON) ou Eventos (CSV)')
    parser.add_argument('--no-intel', action='store_true', help='Ignora a checagem automática de Threat Intelligence')
    args = parser.parse_args()

    print("\n" + "="*50)
    print("🤖 AUTOMAÇÃO DE ANÁLISE SOC (iT.EAM)")
    print("="*50 + "\n")

    if not os.path.exists(args.file):
        print(f"[!] Arquivo não encontrado: {args.file}")
        sys.exit(1)

    # 1. Extração
    print("[*] Extraindo informações chaves...")
    fields = process_payload(args.file)
    print(" ✔ Concluído.\n")

    # 2. Threat Intel
    intel_results = ""
    if not args.no_intel and fields["IOCs"]:
        print(f"[*] Encontrados {len(fields['IOCs'])} IPs públicos para verificação...")
        for ioc in fields["IOCs"][:3]: # Limita a 3 par evitar demora
            intel_results += f"[{ioc}]:\n{run_threat_intel(ioc)}\n\n"
        print(" ✔ TI concluído.\n")
    elif not fields["IOCs"]:
        print("[*] Nenhuma rede externa/IP público encontrado para extrair contexto TI.\n")

    # 3. Modelagem de Drafts
    print("[*] Gerando Notas baseadas nas regras do SOP...\n")
    tp, btp, fp = generate_drafts(fields, intel_results.strip())
    
    print(tp)
    print("\n\n" + btp)
    print("\n\n" + fp)
    
    print("\n[*] Lembrete de restrições de formatação (SOP):")
    print("- Nunca use negrito, itálico ou formatação extra.")
    print("- Garanta a acentuação correta e uso rigoroso de N/A.")
    print("- O Timezone de São Paulo já foi aplicado automaticamente no draft de TP.")

if __name__ == '__main__':
    main()
