# PRD - CLI Interativa do SOCC no estilo OpenClaw

## 1. Resumo executivo

Este documento define a evolucao da CLI do SOCC para um fluxo interativo e guiado, inspirado na experiencia do OpenClaw, mas adaptado ao papel real do SOCC como runtime local de apoio ao analista SOC.

Hoje o projeto ja possui comandos funcionais como `socc onboard`, `socc doctor`, `socc service`, `socc gateway`, `socc dashboard`, `socc runtime` e `socc vantage`. O proximo passo e transformar esses comandos em uma experiencia interativa de verdade, com prompts, validacoes, defaults seguros, persistencia de configuracao e capacidade de conduzir o usuario ate um runtime funcional sem depender de leitura manual do README.

## 2. Contexto

O SOCC ja opera como runtime instalavel, com bootstrap em `~/.socc`, wrapper npm, manifesto local, controle de servico e camada de configuracao por `.env`.

Apesar disso, a experiencia atual da CLI ainda e predominantemente orientada a flags e saidas estaticas. Ela funciona para quem ja conhece o ambiente, mas ainda nao entrega o mesmo nivel de condução que ferramentas como OpenClaw oferecem no primeiro uso, no diagnostico e no ciclo operacional diario.

## 3. Problema

Hoje o usuario ainda precisa saber de antemao:

- quais variaveis configurar
- qual backend de inferencia escolher
- quais modelos estao instalados e qual usar em cada perfil
- quando iniciar servico, gateway ou dashboard
- como validar se a instalacao realmente ficou saudavel
- onde ficam `workspace`, `logs`, `sessions`, `knowledge base` e configuracoes

Isso gera atrito em onboarding, suporte, troubleshooting e operacao recorrente.

## 4. Visao do produto

Transformar a CLI do SOCC em um copiloto operacional local, capaz de:

- guiar o usuario no primeiro uso
- detectar e explicar problemas do ambiente
- sugerir defaults seguros e produtivos
- permitir revisar e salvar configuracoes sem editar arquivo manualmente
- facilitar o ciclo `instalar -> configurar -> validar -> iniciar -> abrir`
- manter compatibilidade com modo nao interativo para scripts e automacao

## 5. Objetivos

### Objetivos de produto

- tornar `socc onboard` um wizard real de configuracao
- tornar `socc doctor` uma experiencia de diagnostico guiado
- tornar `socc service/gateway/dashboard` mais assistivos
- reduzir dependencia de README para tarefas basicas
- manter o runtime reprodutivel e amigavel para operacao humana

### Objetivos de experiencia

- menos flags obrigatorias
- mais prompts contextuais
- resumo final claro do que sera salvo ou executado
- defaults consistentes com o ambiente local
- degradacao elegante em ambiente nao interativo

## 6. Nao objetivos

Esta fase nao pretende:

- remover o modo nao interativo da CLI
- substituir a interface web
- replicar integralmente a CLI do OpenClaw
- adicionar automacao externa via n8n
- criar dependencia obrigatoria de bibliotecas TUI complexas

## 7. Usuarios alvo

- analista SOC que quer instalar e usar o SOCC sem decorar flags
- operador tecnico que precisa diagnosticar backend, modelos e servico local
- mantenedor do runtime que precisa configurar Vantage, agente e modelo por ambiente

## 8. Comandos no escopo

### 8.1 `socc onboard`

Deve virar um wizard interativo com etapas como:

- escolher ou confirmar `SOCC_HOME`
- detectar layout atual e reaproveitar runtime existente
- escolher backend de inferencia
- detectar GPU e confirmar preferencia de device
- detectar modelos locais instalados e mapear `Fast`, `Balanced`, `Deep`
- configurar integracao com Vantage
- escolher agente ativo
- decidir se inicia o servico ao final
- decidir se abre o dashboard ao final

### 8.2 `socc doctor`

Deve suportar modo interativo com:

- checklist visual de saude
- detalhes sob demanda por categoria
- recomendacoes acionaveis
- possibilidade de corrigir pendencias simples no ato
- probe guiado de backend e Vantage

### 8.3 `socc service` e `socc gateway`

Devem ficar mais assistivos com:

- prompts quando faltarem host, porta ou log-level
- confirmacao contextual em restart/stop
- explicacao do estado atual antes da acao
- sugestao de proximo passo apos start ou status

### 8.4 `socc dashboard`

Deve permitir:

- abrir a UI diretamente quando o servico estiver pronto
- oferecer iniciar o servico se ele nao estiver rodando
- explicar qual URL sera usada e por que

### 8.5 `socc runtime`, `socc vantage` e futura `socc configure`

Devem evoluir para:

- inspecao interativa de backend, modelos e capacidades
- revisao guiada dos modulos do Vantage
- ajuste manual de variaveis sensiveis via prompt seguro
- persistencia assistida em `~/.socc/.env`

## 9. Principios de UX da CLI

- interativo por padrao quando houver TTY
- nao interativo por padrao quando receber flags suficientes ou estiver em pipeline
- prompts curtos, com defaults claros
- segredos sempre com input oculto
- confirmar alteracoes antes de salvar
- mostrar diff/resumo das configuracoes geradas
- oferecer “pular por enquanto” quando fizer sentido
- sempre terminar com “o que foi feito” e “proximo passo”

## 10. Requisitos funcionais

### RF-01 Detecao de modo

A CLI deve detectar TTY e escolher entre modo interativo e nao interativo sem quebrar scripts existentes.

### RF-02 Prompt engine reutilizavel

O runtime deve ter uma camada comum para perguntas, confirmacoes, seletores, input secreto e resumo final.

### RF-03 Persistencia segura

As alteracoes interativas devem ser persistidas no `~/.socc/.env`, manifesto e metadados do runtime sem sobrescrever silenciosamente configuracoes sensiveis.

### RF-04 Wizard de onboarding

`socc onboard` deve conduzir o usuario por um fluxo completo de configuracao inicial e validacao basica do ambiente.

### RF-05 Diagnostico guiado

`socc doctor` deve exibir saude do runtime por categorias e permitir navegar pelos detalhes de cada uma.

### RF-06 Acoes operacionais assistidas

`socc service`, `socc gateway` e `socc dashboard` devem sugerir acao adequada com base no estado atual.

### RF-07 Configuracao de inferencia

O fluxo interativo deve permitir escolher backend, device, modelos por perfil e warm-up inicial.

### RF-08 Configuracao do Vantage

O fluxo interativo deve permitir habilitar Vantage, registrar URL/base, escolher metodo de autenticacao e revisar modulos ativos.

### RF-09 Selecao manual de agente

O onboarding deve permitir escolher o agente ativo entre os workspaces disponiveis.

### RF-10 Resumo final acionavel

Ao final de cada fluxo interativo, a CLI deve mostrar:

- o que foi salvo
- o que falhou
- quais comandos executar em seguida

## 11. Requisitos nao funcionais

- compatibilidade com Linux e terminais comuns
- sem obrigar dependencias pesadas de TUI
- saida legivel tanto em PT-BR quanto em modo tecnico enxuto
- logs sem vazar tokens, chaves ou segredos
- possibilidade de testes automatizados por camada de prompt

## 12. Arquitetura proposta

### 12.1 Componentes

- `prompt_runtime`: perguntas, seletores, confirmacoes, senha, menus
- `interactive_flows`: orquestracao de `onboard`, `doctor`, `service`, `dashboard`, `vantage`
- `runtime_config`: leitura/escrita segura de `.env` e manifesto
- `capability_discovery`: GPU, backend, modelos, Vantage, agente, servico
- `summary_renderer`: resumo final e proximo passo

### 12.2 Estrategia de compatibilidade

- flags continuam valendo
- `--json` continua prevalecendo
- `--yes` ou equivalente deve suprimir prompts futuros
- o modo interativo so assume controle quando houver TTY e ausencia de flags suficientes

## 13. Fluxo alvo de referencia

### Fluxo 1 - Primeiro uso

1. Usuario roda `socc onboard`
2. CLI detecta runtime local e pergunta se reaproveita ou recria
3. CLI detecta backend/modelos/GPU
4. Usuario escolhe perfis de modelo e integra Vantage
5. CLI salva configuracao
6. CLI executa validacao basica
7. CLI pergunta se deve iniciar servico
8. CLI pergunta se deve abrir dashboard

### Fluxo 2 - Suporte

1. Usuario roda `socc doctor`
2. CLI mostra checklist por categoria
3. Usuario expande o item com problema
4. CLI sugere correcao ou proximo comando
5. Usuario escolhe aplicar ou deixar pendente

### Fluxo 3 - Operacao diaria

1. Usuario roda `socc dashboard`
2. Se o servico estiver parado, CLI oferece iniciar
3. Depois disso, oferece abrir a interface

## 14. Fases de entrega

### Fase C1 - Fundacao interativa

- runtime de prompts reutilizavel
- deteccao de TTY
- inputs seguros
- sumario final

### Fase C2 - Onboard guiado

- wizard completo de onboarding
- persistencia de backend, modelos, agente e Vantage
- acoes finais opcionais

### Fase C3 - Doctor guiado

- checklist interativo
- probe por categoria
- correcao assistida de pendencias simples

### Fase C4 - Service/Dashboard assistidos

- prompts contextuais
- start/restart/open com menos atrito
- mensagens de estado mais operacionais

### Fase C5 - Configuracao recorrente

- runtime/vantage/configure interativos
- revisao de modulos, modelos e secrets

## 15. Criterios de aceite

- um usuario novo consegue sair do zero ate o dashboard com `socc onboard`
- um usuario antigo consegue revisar saude do ambiente sem ler README
- a CLI nao quebra scripts existentes
- segredos nao aparecem em log nem em resumo final
- o fluxo de Vantage e inferencia fica configuravel sem editar arquivo manualmente

## 16. Dependencias e riscos

### Dependencias

- camada atual de leitura/escrita de `.env`
- discovery de modelos e backend ja existente
- gerenciamento atual de servico local
- catalogo atual de agentes e modulos do Vantage

### Riscos

- UX excessivamente longa no terminal
- ambiguidade entre modo interativo e nao interativo
- regressao em comandos usados por script
- persistencia parcial de configuracao em caso de falha no meio do wizard

## 17. Medidas de sucesso

- reducao no numero de passos manuais apos instalacao
- reducao de erros de configuracao de backend/modelo/Vantage
- menor dependencia do README para operacao basica
- onboarding completado com menos friccao em ambiente novo
