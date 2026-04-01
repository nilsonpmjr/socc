# SOC Copilot - Inventário de Regras e Modelos do MVP

Este documento consolida a fonte da verdade operacional para o `SOC Copilot` no `MVP`, baseada em:

- `.agents/rules/AGENT.md`
- `.agents/rules/TOOLS.md`
- `.agents/workflows/SOP.md`
- exceções por cliente
- modelos existentes em `Modelos\`

O objetivo deste inventário é servir como insumo direto para o `Rule Pack Loader`, para o `Draft Engine` e para os testes de conformidade da saída final.

## 1. Hierarquia de Precedência

Quando houver conflito entre instruções, a ferramenta deve obedecer esta ordem:

1. Classificação e restrições definidas em `AGENT.md`
2. Regras de uso de ferramentas definidas em `TOOLS.md`
3. Fluxo e formato definidos em `SOP.md`
4. Modelo existente mais aderente em `Modelos\`

Regra complementar:

- Se um modelo conflitar com `AGENT.md` em restrição, classificação, anonimização ou segurança operacional, prevalece `AGENT.md`.
- O modelo deve ser usado principalmente para estrutura, tom, vocabulário e ordem dos blocos.

## 2. Diretrizes Core

### 2.1. Determinismo Textual

- A saída final deve ser entregue em texto puro, sem markdown.
- São proibidos caracteres de formatação como `**`, `__` e `#`.
- O idioma é obrigatoriamente `Português do Brasil`.
- Ortografia correta é requisito de aceite.
- Saídas sem acentuação ou sem cedilha são inválidas.

### 2.2. Tempo e Localidade

- Horários em UTC devem ser convertidos para o fuso de São Paulo.
- No corpo descritivo, o formato padrão é `HH:MM:SS`.
- Não incluir observações como `GMT-3`, `Horário de São Paulo` ou equivalentes, salvo se o modelo exigir explicitamente.

### 2.3. Anonimização Protetiva

- A seção final de recomendação não deve expor:
  - IP interno do cliente
  - e-mail do cliente
  - hostname sensível
  - nomes reais de ativos internos
  - dados de payload desnecessários à remediação
- Substituições recomendadas:
  - `ativo impactado`
  - `usuário envolvido`
  - `servidor analisado`
  - `caixa do usuário envolvido`

### 2.4. Acionamento de Threat Intelligence

- Nenhum IP privado deve ser processado em TI por padrão.
- IOC único externo: usar `threat_check.py --dashboard`
- Lote de IOCs externos: usar `batch.py`
- Nunca consultar o mesmo IOC duas vezes por ferramentas diferentes.
- Falhas de TI devem ser registradas como limitação operacional, nunca compensadas por inferência.

## 3. Estrutura de Classificações e Saída

## 3.1. True Positive (TP) - Alerta Completo

### Pré-condição

- atividade maliciosa confirmada ou fortemente suspeita com evidência suficiente

### Estrutura obrigatória

- `Prezados,`
- linha em branco
- `Título`
- `Narrativa do Evento`
- `Detalhes do Evento`
  - `Usuário:`
  - `IP de Origem:`
  - `Destino:` ou `Arquivo/Porta:`
  - `Diretório/Caminho:` quando aplicável
  - `Log Source:`
- `Análise do IP:` quando houver IOC de rede relevante para a conclusão
- `Análise Técnica:`
- `Em anexo o Payload.`
- `Referência:`
- `Referência MITRE:`
- `Recomendação:`

### Regras específicas

- `Análise do IP:` nunca deve aparecer vazia.
- O bloco `Análise do IP:` deve existir quando houver IOC de rede relevante para a conclusão, mesmo que o contexto seja benigno, explicativo ou de descarte técnico.
- Se não houver IOC de rede relevante, o bloco inteiro deve ser omitido.
- `Recomendação:` deve ser um parágrafo fluido, preferencialmente iniciado por `Recomendamos ...`.

## 3.2. Benign True Positive (BTP) - Encerramento Administrativo

### Pré-condição

- a regra disparou corretamente para algo real, porém benigno ou esperado

### Estrutura obrigatória

- sem saudação
- `Classificação Final: Benign True Positive`
- `Resumo Técnico:`
- `Justificativa da benignidade:`
- `Ação de encerramento:`

## 3.3. False Positive / True Negative / Log Transmission Failure

### Pré-condição

- regra inadequada
- evento sem sustentação de incidente
- falha de log, parsing ou transmissão

### Estrutura obrigatória

- sem saudação
- `Classificação Final:`
- `Justificativa:`
- `Ação recomendada:` quando aplicável

## 4. Exceções por Cliente

### Icatu

- Para `Icatu`, a ferramenta não deve sugerir encerramento administrativo por padrão quando a operação do cliente exigir continuidade da tratativa pelo time interno deles.
- Nesses casos, a saída correta é um `alerta de repasse técnico`.
- O alerta de repasse técnico mantém a classificação técnica real do caso, mas adapta a narrativa para explicitar que a validação final cabe ao time de Segurança do cliente.
- O tom deve ser objetivo e não deve afirmar comprometimento confirmado quando a evidência não sustentar isso.

## 5. Modelos Existentes em `Modelos\`

O diretório `Modelos\` contém `79` referências no momento deste inventário. Esses modelos devem ser usados para recuperar a ordem dos blocos, o tom narrativo, e as recomendações padrão anonimizadas.

### 5.1. Agrupamentos por Tipo de Incidente

- **Acesso e Autenticação (AD / Azure / AWS)**
  - `Falhas de Logon`, `Criação de Contas - AD`, `Adição de Membro`, `Membro Removido de Grupo`, `Acesso RDP`, `Bloqueio por Acesso Condicional`, `Desativação em massa de MFA`, `Acesso não autorizado AWS`, `Alteração em grupo crítico do AWS`.

- **Rede e Conectividade (Darktrace / FW / Scan)**
  - `Darktrace`, `Darktrace2`, `Darktrace3`, `Port Scanning`, `Varredura de portas`, `Ping Sweep`, `DNS PTR Scan`, `Protocolo TelNet`, `Scan Cisco`, `Varredura originada de VPN`, `Botnet`.

- **Ameaças e Malware (EDR / AV / IPS)**
  - `Vision One`, `SentinelOne`, `Microsoft Defender`, `Execução de Código Malicioso`, `Possible Worm`, `Software potencialmente indesejado`, `Resolução de DNS DGA`, `Possível Phishing`, `snort`, `Dupla Extensão`.

- **Exfiltração e DLP (Cloud / O365)**
  - `Possível Exfiltração`, `Violação DLP`, `Compartilhamento suspeito`, `Exfiltração2`.

- **Infraestrutura e Configuração**
  - `Alteração de GPO`, `Alteração no Firewall`, `Modificação de Política AWS`, `Service Stop`, `Acesso RDP - Protocolo de Gerenciamento`.

### 5.2. Regra Prática de Uso

1. **Prioridade de Match**: Se houver um modelo cujo nome coincida com o comportamento da ofensa, use-o como base primária.
2. **Fallback por Fonte de Log**: Se não houver match por comportamento, use o modelo da fonte de log correspondente (ex: `Vision One`, `Darktrace`, `Office 365`).
3. **Fallback SOP**: Na ausência de qualquer modelo aderente, siga rigorosamente a estrutura definida no `SOP.md`.

## 6. Checklist de Validação da Saída Final

Antes de considerar uma saída válida, o sistema deve verificar:

- [ ] o texto está em português
- [ ] a acentuação e a cedilha estão corretas
- [ ] não há markdown
- [ ] a classificação final está presente
- [ ] o timezone foi convertido corretamente
- [ ] a estrutura de saída corresponde ao tipo (`TP`, `BTP`, `FP`, `TN`, `LTF` ou repasse técnico)
- [ ] `Análise do IP:` só aparece quando há conteúdo relevante
- [ ] `Análise Técnica:` está presente nos alertas completos
- [ ] `Referência:` e `Referência MITRE:` estão presentes quando aplicáveis
- [ ] `Recomendação:` está anonimizada
- [ ] não há dados sensíveis indevidos na recomendação
- [ ] a exceção do cliente, se houver, foi respeitada
- [ ] o modelo aderente foi usado quando disponível

## 7. Observações de Implementação

- Este inventário é um documento de `MVP`, não de Fase 2.
- Ele deve ser mantido sincronizado com `.agents`.
- Qualquer mudança em regra, estrutura de saída ou exceção por cliente deve refletir aqui e no conjunto de testes.

---

✅ `Checkpoint MVP`: Inventário consolidado e alinhado ao PRD e à TODO-list.
