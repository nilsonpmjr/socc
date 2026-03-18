# SOC Copilot - TODO Geral de Implementação

Este documento consolida o plano do `MVP` e da `Fase 2` para evitar perda de contexto durante a execução do projeto.

## Diretriz de uso

- Cada fase deve ter um `responsável primário`.
- Sempre que uma fase terminar, o responsável deve registrar:
  - status
  - arquivos alterados
  - decisões tomadas
  - riscos remanescentes
- Mudanças de regra, SOP, templates e contratos da semi-LLM devem ser revisadas antes de avançar para a próxima fase.

## Papéis recomendados por agente

### Claude-code Opus 4.6

Melhor uso:

- arquitetura
- revisão crítica de fluxos
- validação de edge cases
- revisão de qualidade e consistência entre documentos e código
- desenho de contratos e critérios de aceite

### Gemini 3.1 Pro

Melhor uso:

- síntese de grande volume de contexto
- organização documental
- inventário de regras, modelos e fluxos
- preparação de datasets e casos de teste
- mapeamento de comportamento por cliente, regra e saída

### Codex GPT-5.4

Melhor uso:

- implementação prática no repositório
- estruturação do backend
- integração entre módulos
- refino incremental com testes
- debugging e ajustes orientados ao código real

---

# Fase 1 - MVP

## 1. Fechamento do escopo do MVP

### Objetivo

Congelar o que entra e o que não entra no MVP para evitar deriva de produto.

### TODO

- [ ] Revisar `SOC_Copilot_PRD.md` e congelar o escopo funcional do MVP.
- [ ] Confirmar entradas obrigatórias, saídas esperadas e critérios de aceite.
- [ ] Confirmar política de persistência mínima.
- [ ] Confirmar se a classificação final será sempre validada pelo analista.

### Responsável primário

`Claude-code Opus 4.6`

### Apoio

`Codex GPT-5.4`

---

## 2. Inventário das regras reais

### Objetivo

Mapear todas as regras operacionais que o sistema deve respeitar desde o primeiro dia.

### TODO

- [x] Consolidar regras de `AGENT.md`, `TOOLS.md`, `SOP.md` e exceções por cliente.
- [x] Listar estruturas válidas de saída para `TP`, `BTP`, `FP`, `TN`, `LTF` e repasse técnico.
- [x] Mapear diferenças por cliente, com destaque para `Icatu`.
- [x] Identificar modelos existentes em `Modelos\` por tipo de ofensa.
- [x] Criar checklist de validação da saída final.

### Responsável primário

`Gemini 3.1 Pro`

### Revisor

`Claude-code Opus 4.6`

---

## 3. Desenho técnico do MVP

### Objetivo

Traduzir o PRD em arquitetura implementável.

### TODO

- [x] Definir estrutura de pastas do projeto.
- [x] Definir módulos:
  - input adapter
  - parser engine
  - rule pack loader
  - threat intel adapter
  - classification helper
  - semi-LLM adapter
  - draft engine
  - persistence layer
- [x] Definir contratos entre os módulos.
- [x] Definir endpoints FastAPI e fluxo de UI.
- [x] Definir schema SQLite do MVP.

Entregável:

- `Automacao/SOC_Copilot_Desenho_Tecnico_MVP.md`

### Responsável primário

`Codex GPT-5.4`

### Revisor

`Claude-code Opus 4.6`

---

## 4. Parser e normalização

### Objetivo

Implementar a camada determinística mais importante do sistema.

### TODO

- [x] Refatorar ou absorver a lógica atual de `analise_ofensa.py`.
- [x] Suportar entrada em texto, JSON e CSV.
- [x] Normalizar horário, usuário, IP, destino, diretório e log source.
- [x] Classificar IOCs internos e externos.
- [x] Implementar defang seguro.
- [x] Criar fallback para payloads malformados.

Entregáveis:

- `soc_copilot/modules/input_adapter.py`
- `soc_copilot/modules/parser_engine.py`

### Responsável primário

`Codex GPT-5.4`

### Apoio documental

`Gemini 3.1 Pro`

---

## 5. Rule Pack Loader

### Objetivo

Carregar regras locais de forma determinística e confiável.

### TODO

- [x] Ler `.agents/rules`.
- [x] Ler `.agents/workflows/SOP.md`.
- [x] Mapear exceções por cliente.
- [x] Carregar modelos equivalentes em `Modelos\`.
- [x] Expor um objeto consolidado de regras para o restante do sistema.

Entregáveis:

- `soc_copilot/modules/rule_loader.py`
- `soc_copilot/config.py`

### Responsável primário

`Codex GPT-5.4`

### Revisor

`Claude-code Opus 4.6`

---

## 6. Integração Threat Intelligence

### Objetivo

Padronizar o uso de `threat_check.py` e `batch.py` sem duplicidade nem ruído.

### TODO

- [x] Implementar decisão automática entre IOC único e lote.
- [x] Garantir que `batch.py` só rode quando houver mais de um IOC.
- [x] Evitar consultar o mesmo IOC duas vezes.
- [x] Implementar timeout e tratamento de falha.
- [x] Resumir o resultado para o bloco `Análise do IP:`.

Entregáveis:

- `soc_copilot/modules/ti_adapter.py`
- `soc_copilot/config.py`
- `soc_copilot/main.py`

### Responsável primário

`Codex GPT-5.4`

### Revisor

`Claude-code Opus 4.6`

---

## 7. Contrato da semi-LLM

### Objetivo

Implementar apoio analítico sem deixar a semi-LLM assumir o controle da saída.

### TODO

- [x] Definir schema fixo da entrada.
- [x] Definir schema fixo da saída em JSON.
- [x] Limitar a semi-LLM a:
  - resumo factual
  - hipóteses ranqueadas
  - lacunas
  - classificação sugerida
  - MITRE candidata
  - alertas de qualidade
- [x] Impedir geração de texto final livre.
- [x] Validar a resposta contra schema antes de usar.

### Responsável primário

`Claude-code Opus 4.6`

### Implementação

`Codex GPT-5.4`

---

## 8. Draft Engine

### Objetivo

Gerar as saídas finais no formato operacional correto.

### TODO

- [x] Criar templates controlados para `TP`, `BTP`, `FP`, `TN`, `LTF`.
- [x] Criar template de repasse técnico para `Icatu`.
- [x] Garantir ordem correta dos blocos.
- [x] Garantir acentuação e cedilha.
- [x] Garantir ausência de markdown.
- [x] Garantir anonimização nas recomendações.
- [x] Garantir que `Análise do IP:` só apareça quando houver conteúdo.

### Responsável primário

`Codex GPT-5.4`

### Revisor funcional

`Claude-code Opus 4.6`

---

## 9. Interface do MVP

### Objetivo

Entregar uma interface simples, rápida e útil.

### TODO

- [x] Criar formulário de entrada.
- [x] Exibir campos extraídos.
- [x] Exibir análise estruturada.
- [x] Exibir saída final.
- [x] Implementar `Copiar`.
- [x] Implementar `Salvar`.
- [x] Garantir boa usabilidade sem bibliotecas pesadas.

### Responsável primário

`Codex GPT-5.4`

### Apoio de organização de conteúdo

`Gemini 3.1 Pro`

---

## 10. Casos de teste e dataset

### Objetivo

Criar a base de validação do MVP.

### TODO

- [x] Montar suíte de casos anonimizados.
- [x] Cobrir:
  - JSON
  - CSV
  - texto bruto
  - IOC único
  - múltiplos IOCs
  - IP privado
  - `TP`
  - `BTP`
  - `FP`
  - `TN`
  - `LTF`
  - `Icatu`
- [x] Criar expected outputs mínimos.
- [x] Criar checklist de conformidade textual.

### Responsável primário

`Gemini 3.1 Pro`

### Revisor

`Claude-code Opus 4.6`

---

## 11. Testes, revisão e hardening do MVP

### Objetivo

Fechar o MVP com segurança e previsibilidade.

### TODO

- [x] Executar testes de regressão.
- [ ] Corrigir divergências de estrutura de saída.
- [ ] Validar comportamento da semi-LLM com casos faltantes.
- [ ] Revisar segurança local e persistência.
- [ ] Validar performance.
- [x] Produzir checklist de go-live local.

### Responsável primário

`Claude-code Opus 4.6`

### Implementação das correções

`Codex GPT-5.4`

---

# Fase 2

## 12. Busca histórica

### Objetivo

Adicionar consulta de execuções passadas e saídas anteriores.

### TODO

- [ ] Definir retenção de dados.
- [ ] Expandir schema SQLite.
- [ ] Criar filtros por cliente, regra, IOC, usuário e ativo.
- [ ] Criar interface de consulta histórica.

### Responsável primário

`Codex GPT-5.4`

### Planejamento e revisão

`Claude-code Opus 4.6`

---

## 13. Similaridade de casos

### Objetivo

Recuperar casos parecidos para apoiar triagem e classificação.

### TODO

- [ ] Definir critérios de similaridade estruturada.
- [ ] Criar ranking de casos semelhantes.
- [ ] Expor explicação do porquê da similaridade.
- [ ] Garantir que a similaridade não decida o caso sozinha.

### Responsável primário

`Gemini 3.1 Pro`

### Implementação

`Codex GPT-5.4`

---

## 14. Similaridade semântica local

### Objetivo

Adicionar embeddings ou vetores locais, se realmente fizer sentido.

### TODO

- [ ] Avaliar custo-benefício.
- [ ] Escolher stack local.
- [ ] Criar fallback semântico opcional.
- [ ] Garantir zero envio de dados para nuvem.

### Responsável primário

`Claude-code Opus 4.6`

### Implementação

`Codex GPT-5.4`

---

## 15. Memória operacional por cliente

### Objetivo

Melhorar adaptação do sistema a exceções recorrentes.

### TODO

- [ ] Mapear exceções por cliente.
- [ ] Separar exceções globais de exceções locais.
- [ ] Criar mecanismo de leitura controlada da memória operacional.
- [ ] Evitar que memória informal vire regra global sem revisão.

### Responsável primário

`Gemini 3.1 Pro`

### Revisor

`Claude-code Opus 4.6`

---

## 16. Tuning assistido

### Objetivo

Ajudar a operação a identificar regras ruidosas e padrões benignos recorrentes.

### TODO

- [ ] Detectar regras com muitos `FP`.
- [ ] Detectar entidades benignas recorrentes.
- [ ] Sugerir tuning com base em evidência.
- [ ] Separar tuning global de tuning por cliente.

### Responsável primário

`Claude-code Opus 4.6`

### Implementação

`Codex GPT-5.4`

---

## 17. Evolução da semi-LLM

### Objetivo

Ampliar inteligência sem perder controle operacional.

### TODO

- [ ] Permitir comparação com casos históricos.
- [ ] Sugerir divergências entre ferramentas.
- [ ] Sugerir hunting adicional contextual.
- [ ] Manter saída sempre estruturada.
- [ ] Revalidar contratos e limites.

### Responsável primário

`Claude-code Opus 4.6`

### Apoio de contexto

`Gemini 3.1 Pro`

### Implementação

`Codex GPT-5.4`

---

## 18. Avaliação de MCP

### Objetivo

Decidir se MCP passa a ser útil na Fase 2.

### TODO

- [ ] Avaliar necessidade real de servir contexto para múltiplos agentes.
- [ ] Avaliar se rules, modelos e histórico devem sair do filesystem puro.
- [ ] Avaliar custo operacional adicional.
- [ ] Decidir com base em uso real do MVP.

### Responsável primário

`Claude-code Opus 4.6`

### Apoio documental e comparativo

`Gemini 3.1 Pro`

---

## 19. Revisão final da Fase 2

### Objetivo

Evitar que a expansão comprometa a previsibilidade conquistada no MVP.

### TODO

- [ ] Revalidar todos os contratos.
- [ ] Executar regressão completa.
- [ ] Confirmar que a saída final continua controlada por templates.
- [ ] Validar que a semi-LLM não passou a governar o sistema.

### Responsável primário

`Claude-code Opus 4.6`

### Correções finais

`Codex GPT-5.4`

---

# Ordem recomendada de condução

1. `Claude-code Opus 4.6` fecha escopo, contratos e revisão crítica.
2. `Gemini 3.1 Pro` consolida regras, modelos, inventário e casos de teste.
3. `Codex GPT-5.4` implementa o MVP no repositório.
4. `Claude-code Opus 4.6` revisa o MVP pronto e trava critérios de Fase 2.
5. `Gemini 3.1 Pro` organiza memória, similaridade e base histórica.
6. `Codex GPT-5.4` implementa a Fase 2 de forma incremental.
