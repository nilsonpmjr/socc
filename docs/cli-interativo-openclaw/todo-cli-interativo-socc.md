# TODO - CLI Interativa do SOCC no estilo OpenClaw

## Objetivo

Levar a CLI do SOCC de um conjunto de comandos funcionais para uma experiencia interativa e assistida, com foco em onboarding, diagnostico e operacao recorrente do runtime local.

## Premissas

- a CLI atual ja possui `onboard`, `doctor`, `service`, `gateway`, `dashboard`, `runtime` e `vantage`
- o runtime atual ja persiste estado em `~/.socc`
- o projeto precisa manter compatibilidade com modo nao interativo
- a experiencia deve ser inspirada no OpenClaw, mas adaptada ao fluxo operacional do SOCC

## Fase C0 - Fundacao da CLI interativa

- [ ] Mapear todos os comandos que podem entrar em modo interativo
- [ ] Definir a regra de deteccao de TTY versus modo scriptado
- [ ] Criar camada comum de prompts reutilizaveis
- [ ] Criar input seguro para segredos e tokens
- [ ] Criar componente de confirmacao final antes de salvar configuracoes
- [ ] Criar renderer de resumo final com proximos passos
- [ ] Definir estrategia de cancelamento e retomada do wizard

## Entregavel C0

- infraestrutura de prompts pronta para ser reutilizada por varios comandos

## Fase C1 - `socc onboard` interativo

- [ ] Quebrar o onboarding em etapas pequenas e navegaveis
- [ ] Detectar runtime existente e oferecer reaproveito ou recriacao
- [ ] Permitir escolher ou confirmar `SOCC_HOME`
- [ ] Detectar backends disponiveis e sugerir um padrao
- [ ] Detectar GPU e propor preferencia de device
- [ ] Detectar modelos instalados e mapear `Fast`, `Balanced`, `Deep`
- [ ] Permitir configurar ou pular integracao com Vantage
- [ ] Permitir escolher o agente ativo
- [ ] Mostrar diff/resumo do que sera salvo no `.env`
- [ ] Oferecer iniciar servico e abrir dashboard ao final
- [ ] Garantir fallback limpo para modo nao interativo

## Entregavel C1

- `socc onboard` funcionando como wizard real de primeira configuracao

## Fase C2 - `socc doctor` interativo

- [ ] Organizar o doctor por categorias: runtime, inferencia, modelos, Vantage, agente, servico, KB
- [ ] Exibir checklist resumido com status por categoria
- [ ] Permitir expandir detalhes sob demanda
- [ ] Exibir recomendacoes acionaveis por problema encontrado
- [ ] Permitir executar probes opcionais a partir do fluxo interativo
- [ ] Permitir aplicar correcoes simples no ato quando seguro
- [ ] Mostrar resumo final com pendencias remanescentes

## Entregavel C2

- `socc doctor` com experiencia guiada de diagnostico e troubleshooting

## Fase C3 - `socc service`, `socc gateway` e `socc dashboard`

- [ ] Tornar `service start` assistivo quando host/porta nao forem passados
- [ ] Mostrar o estado atual antes de `restart` ou `stop`
- [ ] Pedir confirmacao contextual para acoes potencialmente disruptivas
- [ ] Fazer `dashboard` oferecer iniciar servico se ele estiver parado
- [ ] Fazer `dashboard --open` explicar o fallback de URL escolhido
- [ ] Melhorar a mensagem final de start com URL, logs e proximos comandos
- [ ] Garantir que o alias `gateway` acompanhe a mesma UX de `service`

## Entregavel C3

- comandos operacionais mais conversacionais e menos dependentes de memorizacao de flags

## Fase C4 - `runtime`, `vantage` e futura `configure`

- [ ] Tornar `runtime` navegavel para revisar backend, modelos e capacidades
- [ ] Permitir warm-up guiado de modelo pelo terminal
- [ ] Tornar `vantage` interativo para revisar modulos ativos
- [ ] Permitir registrar URL e token/API key via prompt seguro
- [ ] Permitir testar conectividade e mostrar o resultado por modulo
- [ ] Avaliar a criacao de `socc configure` como hub de ajustes recorrentes

## Entregavel C4

- camada de configuracao recorrente pronta para administracao humana do runtime

## Fase C5 - Robustez e qualidade

- [ ] Adicionar testes unitarios da camada de prompts
- [ ] Adicionar testes de integracao para fluxos interativos com stubs
- [ ] Cobrir cenarios de cancelamento no meio do wizard
- [ ] Cobrir persistencia parcial e rollback seguro
- [ ] Documentar modo interativo e modo nao interativo
- [ ] Atualizar README com fluxos guiados reais

## Entregavel C5

- CLI interativa validada, documentada e pronta para rollout gradual

## Regras de compatibilidade

- [ ] `--json` deve continuar suprimindo prompts
- [ ] flags explicitas devem continuar prevalecendo sobre defaults interativos
- [ ] o comportamento atual de scripts nao deve quebrar
- [ ] deve existir opcao futura para autoaceite (`--yes` ou similar)

## Backlog recomendado

- [ ] tema visual mais rico no terminal com cores/ícones discretos
- [ ] modo wizard de manutencao periodica
- [ ] historico de configuracoes aplicadas
- [ ] exportar relatorio do doctor em formato markdown/json
- [ ] permitir preset por perfil de ambiente

## Criterios de pronto

- [ ] `socc onboard` guia um usuario novo ate um runtime funcional
- [ ] `socc doctor` explica problemas e proximos passos com clareza
- [ ] `socc dashboard` e `socc service` reduzem atrito operacional
- [ ] segredos nunca aparecem em tela ou log em claro
- [ ] a CLI continua utilizavel por scripts e CI sem regressao
