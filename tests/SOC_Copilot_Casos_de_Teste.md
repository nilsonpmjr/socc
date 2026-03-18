# SOC Copilot MVP - Suíte de Testes e Conformidade

Este documento detalha os cenários de validação (Test Cases), os resultados mínimos aceitáveis (Expected Outputs) e o Checklist de Conformidade Textual, visando blindar a etapa de regressão do MVP.

## 1. Casos de Teste Estruturados (Dataset MVP)

Os testes automatizados devem utilizar os payloads mapeados no arquivo `dataset_mvp.json`, os quais contêm artefatos anonimizados cobrindo os seguintes cenários operacionais:

| ID | Formato | Cenário Primário | Tipo de IOC | Classificação | Cliente | Validação Esperada |
| --- | --- | --- | --- | --- | --- | --- |
| TC-01 | JSON | Endpoint Block (Darktrace Antigena) | Único (IP Público) | TP | Padrão | Extração correta do Source/Dest IP. Acionamento do `ti_adapter.enrich()`. Geração de alerta TP com bloqueio citado. |
| TC-02 | CSV | QRadar Log Activity (Múltiplos lances) | Múltiplos (MD5, IPs) | TP | Padrão | Adição do bloco "Análise do IP:". Consulta correta ao TI. |
| TC-03 | Text | RAW Syslog / LEEF Sem parser | Nenhum (Malformado) | LTF | Padrão | Geração de Nota de Encerramento (LTF) contendo frase de descarte de ruído no resumo. |
| TC-04 | JSON | Azure AD Impossible Travel | IP Privado / VPN | FP / BTP | Padrão | Supressão total da triagem de TI no backend (skip). Nota de encerramento BTP. |
| TC-05 | CSV | Atividade legítima de Admin on-Prem | Internal IP | TN | Padrão | Nota de Encerramento (TN). Ausência do bloco `Análise do IP:` e de campos irrelevantes. |
| TC-06 | RAW | Alerta de patch interno legítimo | Nenhum | BTP | **Icatu** | Uso do template `Alerta de Encaminhamento Técnico` preservando o fluxo de repasse do cliente. |
| TC-07 | JSON | Alerta anômalo, risco baixo | N/A | BTP / FP | **Icatu** | Proibição do encerramento autônomo. Template de repasse técnico. |
| TC-08 | JSON | Vulnerability Scan (Nessus/Qualys) | IP Privado | FP | Padrão | Nota de Encerramento (FP) validando que scans locais não acionam TI externo. |
| TC-09 | Text | Alerta Crítico (Malware via Sandbox) | Hash | TP | **Icatu** | Alerta TP crítico direcionado ao cliente, acionando o TI_Adapter para o respectivo hash. |

## 2. Expected Outputs (Resultados Mínimos)

A cada execução do teste em `TC-*`, um test runner autônomo (ex: via `pytest`) validará o backend verificando se:

1. Retorna JSON serializável de sucesso (status `200 OK`).
2. Contém as chaves mandatárias em `expected`: comportamentos obrigatórios e textos que devem estar presentes.
3. Valida se a camada determinística de parsing não perdeu campos (Horário em padrão SP, Usuário sem domínio desnecessário, etc.).
4. Valida se o `draft` desarmou adequadamente IPs/URLs ofensivos (ex: `185[.]15[.]20[.]33`).

## 3. Checklist de Conformidade Textual (Draft Engine)

Todo rascunho de texto final gerado pelo backend passará pelas seguintes premissas gramaticais (Checklist):

- [ ] **Acentuação e Ortografia:** Preservação estrita de `.encode("utf-8")` em saídas (sem caracteres ASCII bugados).
- [ ] **Ausência de Markdown Decorativo:** O draft final (`conteudo`) gerado pela Semi-LLM foi sanitizado e não contém negritos (`**`), itálicos (`*`) ou formatação de cabeçalho (`#`).
- [ ] **Formato de Horário Fixo:** Presença obrigatória de strings de hora sob o padão `HH:MM:SS` sem "GMT", "BRT", colchetes ou adendos do tipo "segundo o fuso".
- [ ] **Blocos Obrigatórios Rígidos (TP):** A ordem do TP deve ser sempre: `Prezados > Título > Narrativa > Detalhes > [Análise TI] > Análise Técnica > "Em anexo o Payload." > Referência > Referência MITRE > Recomendação`.
- [ ] **Notas de Encerramento (BTP/TN/LTF/FP):** Devem terminar estritamente nos 4 blocos: `Classificação`, `Resumo Técnico`, `Justificativa da benignidade` e `Ação de encerramento`. Sem blocos em aberto.
- [ ] **Anonimização Plena (Recomendações):** Ausência da palavra real de usuários mapeados ou caminhos absolutos (`C:\Users\...`) na sessão de recomendações.
- [ ] **Verificador MITRE:** Quando aplicável ao `TP`, a técnica informada obedece à regex de formatação `re.fullmatch(r"T\d{4}(?:\.\d{3})?", tecnica)`.
