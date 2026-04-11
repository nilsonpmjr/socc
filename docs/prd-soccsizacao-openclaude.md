# PRD — SOCCsização do Clone do OpenClaude

## 1. Executive Summary

- **Problem Statement**: A base atual em TypeScript/Bun ainda se apresenta como `OpenClaude`, com foco primário em coding-agent generalista, embora o objetivo do produto seja ser o SOCC: uma ferramenta centrada em SOC, threat intelligence e incident response. Isso gera desalinhamento entre identidade, UX, documentação, modelo mental do usuário e postura de segurança.
- **Proposed Solution**: Transformar o clone atual em `SOCC`, usando a stack existente como runtime principal e reaproveitando do legado do SOCC apenas o branding e a alma comportamental presente em `.agents`. A transformação inclui renomeação completa de pacote, binário, superfícies de UX e documentação, além de reposicionar o agente `Socc` como analista de segurança padrão e “alma” do produto, mantendo menções ao OpenClaude apenas onde forem úteis para atribuição, histórico ou licenciamento.
- **Success Criteria**:
  - `socc` passa a ser o único binário/documentação principal de operação, com `socc --help` e `socc --version` funcionais no fluxo padrão.
  - Menções ativas a `OpenClaude` são reduzidas a `0` nas superfícies principais de produto, onboarding, help, docs operacionais e UX, exceto em `README`, `CONTRIBUTING`, `LICENSE` e outros pontos explícitos de atribuição histórica.
  - O fluxo inicial do produto passa a comunicar claramente que o SOCC é um copiloto para SOC/threat intel/incident response, e que capacidades de coding-agent continuam disponíveis como suporte secundário.
  - O agente `Socc` é carregado por padrão com comportamento alinhado ao material de referência: PT-BR por padrão, separação entre observado e inferido, e proibição explícita de inventar IOCs/CVEs/TTPs/fontes.
  - A documentação principal de instalação, uso e arquitetura é reposicionada para segurança e operação SOC, com referência explícita ao legado do OpenClaude apenas onde agregue contexto.

## 2. User Experience & Functionality

- **User Personas**:
  - Analista SOC N1: precisa triagem rápida, respostas curtas, IOCs extraídos, risco provável e próximos passos.
  - Analista SOC N2 / threat hunter: precisa evidência, contexto, TTPs, correlação e separação rigorosa entre fato e inferência.
  - Incident responder: precisa usar o mesmo runtime para investigação, notas técnicas e apoio operacional durante incidentes.
  - Engenheiro mantenedor da plataforma: precisa migrar a base atual sem trocar a stack principal, preservando compatibilidade razoável e reduzindo o risco de regressões.

- **User Stories**:
  - As a SOC analyst, I want to launch `socc` and immediately interact with a security-focused analyst persona so that the tool starts in the right operational context.
  - As an incident responder, I want the assistant to separate observed evidence from inferred conclusions so that I can trust and reuse the analysis in real workflows.
  - As a threat intelligence analyst, I want the product language, commands, docs, and defaults to reflect SOC operations instead of a generic coding CLI so that onboarding matches the actual purpose of the tool.
  - As a maintainer, I want to keep the current TypeScript/Bun runtime while reusing only branding and agent soul artifacts from the legacy SOCC materials so that migration stays narrow and controlled.
  - As a project owner, I want historical attribution to OpenClaude preserved only in appropriate legal/community documents so that the product can establish an independent identity without losing provenance.

- **Acceptance Criteria**:
  - Story 1 is done when the primary executable, help text, startup copy, package metadata and install docs all use `socc` as the canonical command and product name.
  - Story 1 is done when the default active persona is the `Socc` security analyst, not a generic coding assistant persona.
  - Story 2 is done when the default assistant guidance explicitly requires observed-vs-inferred separation, non-invention of security indicators, and concise PT-BR analyst support.
  - Story 2 is done when regression tests or prompt-contract checks validate that high-risk security outputs do not fabricate IOCs, CVEs, hashes, domains, IPs or sources in baseline scenarios.
  - Story 3 is done when onboarding docs, quick starts, README opening sections, command descriptions and in-product labels frame SOCC as a SOC/threat-intel/incident-response copiloto.
  - Story 3 is done when coding-agent features remain available but are described as secondary capabilities in support of the analyst workflow.
  - Story 4 is done when the migration plan keeps the current TypeScript/Bun architecture as the runtime source of truth and explicitly forbids reusing legacy SOCC commands or harness implementations.
  - Story 4 is done when the only approved reuse from the legacy SOCC material is branding guidance and the agent soul/identity artifacts under `.agents`.
  - Story 5 is done when `README`, `CONTRIBUTING`, `LICENSE` and equivalent attribution surfaces may mention OpenClaude as origin/base, while product-facing operational UX no longer depends on that branding.

- **Non-Goals**:
  - Reescrever o runtime principal em Python nesta fase.
  - Buscar paridade total com todos os fluxos históricos de `socc-canonical/` no primeiro ciclo.
  - Reaproveitar comandos, harness, CLI flow ou runtime do SOCC legado.
  - Remover suporte multi-provider existente, desde que ele seja reposicionado como meio e não como identidade do produto.
  - Apagar o histórico de origem do projeto ou remover atribuições necessárias.
  - Transformar o SOCC em uma ferramenta de execução ofensiva ou automação destrutiva por padrão.

## 3. AI System Requirements

- **Tool Requirements**:
  - O sistema deve manter ferramentas gerais necessárias ao runtime agentic atual, mas classificadas como suporte.
  - O sistema deve priorizar ferramentas e fluxos alinhados a SOC, incluindo pelo menos: extração de IOCs, defang/refang, parsing de payloads/textos/logs, pesquisa contextual segura, leitura controlada de arquivos e consultas de threat intel quando configuradas.
  - O sistema deve incorporar a política comportamental do agente `Socc` baseada no material de `socc-canonical/.agents/soc-copilot/`, incluindo identidade, estilo, limites e prioridades de saída.
  - O sistema deve suportar uma superfície de comandos e help coerente com o domínio SOC, mas derivada do runtime atual renomeado, não dos comandos legados do SOCC.
  - O sistema deve manter integração com provedores de modelo compatíveis já existentes, mas com política de segurança explícita sobre segredos, egress e confiabilidade do output.

- **Evaluation Strategy**:
  - Criar uma suíte de prompts de referência com pelo menos `30` cenários cobrindo IOC triage, phishing, payload suspeito, URL suspeita, enriquecimento e perguntas consultivas de SOC.
  - Exigir `>= 95%` de separação correta entre “observado” e “inferido” na avaliação manual/automatizada da suíte.
  - Exigir `0` casos aceitáveis de IOC/CVE/hash/domínio/IP inventado nos cenários de benchmark do agente `Socc`.
  - Exigir `>= 90%` de aderência à persona operacional do SOCC em linguagem, prioridade de saída e próximos passos concretos.
  - Exigir que `100%` das superfícies renomeadas críticas passem em verificação automatizada de branding, cobrindo pacote, binário, docs principais, help, paths e mensagens de erro.

## 4. Technical Specifications

- **Architecture Overview**:
  - O runtime principal permanece a base TypeScript/Bun já presente no repositório.
  - A transformação deve ser realizada em camadas:
    - camada 1: identidade do produto (`OpenClaude` -> `SOCC`);
    - camada 2: identidade do runtime (`openclaude` -> `socc`, package/bin/proto/help/settings/output paths);
    - camada 3: reposicionamento de UX e docs para segurança;
    - camada 4: ativação do agente `Socc` como comportamento padrão;
    - camada 5: incorporação exclusiva do branding e da alma comportamental de `.agents`.
  - `socc-canonical/` não deve ser tratado como fonte de comandos, harness ou runtime. Seu reaproveitamento fica limitado aos artefatos de identidade/comportamento do agente.
  - O modelo operacional desejado é: CLI/TUI/headless runtime security-first, com coding-agent capabilities tratadas como suporte para investigação, automação limitada e produtividade do analista.

- **Integration Points**:
  - Package manager: o pacote publicado deve migrar de `@gitlawb/openclaude` para a identidade final definida do SOCC, com `socc` como binário principal.
  - CLI/runtime: `bin/openclaude`, mensagens de erro, docs de instalação, `README`, quick starts, scripts de smoke e comandos derivados devem ser migrados para `socc`.
  - Configuração local: a solução deve definir uma convenção unificada de paths e arquivos de configuração do SOCC, preferencialmente orientada a `~/.socc` e equivalentes de projeto, com estratégia explícita de migração de paths herdados.
  - gRPC/protocolos: artefatos como `src/proto/socc.proto` e namespaces correlatos devem entrar no inventário de compatibilidade/versionamento para clientes existentes.
  - Persona/agente: o contrato do agente `Socc` deve ser carregável na stack atual a partir de artefatos declarativos ou configuração equivalente, mantendo espaço para futuras especializações.
  - Legado SOCC: comandos, harness e fluxos de runtime do SOCC legado não entram como dependência, baseline nem backlog obrigatório desta transformação.

- **Security & Privacy**:
  - O agente padrão deve proibir invenção de indicadores, fontes ou conclusões não suportadas por evidência.
  - O sistema deve distinguir explicitamente fatos observados, inferências, nível de confiança e próximos passos.
  - Segredos de providers, integrações e backends devem continuar redatados em UI, logs e fluxos de configuração.
  - O reposicionamento para SOC não pode ampliar permissões destrutivas por padrão; qualquer ferramenta de shell/file deve continuar sob política explícita.
  - O produto deve privilegiar local-first quando possível e explicitar quando um fluxo envia dados a provedores externos.
  - A documentação principal deve deixar claro o limite do sistema: apoio ao analista, não substituição de validação humana nem automação de contenção sem revisão.

## 5. Risks & Roadmap

- **Phased Rollout**:
  - MVP:
    - Renomear identidade principal para `SOCC` nas superfícies de produto.
    - Tornar `socc` o binário principal.
    - Reposicionar `README`, quick starts, install docs, help e mensagens iniciais para segurança/SOC.
    - Adaptar o agente `Socc` como persona padrão do runtime.
    - Preservar menções ao OpenClaude apenas em documentos de atribuição, histórico e licença.
  - v1.1:
    - Migrar paths/configurações centrais para convenção `socc`.
    - Consolidar help, onboarding e superfície operacional do runtime atual sob a identidade SOCC.
    - Endurecer verificações automatizadas de branding e segurança comportamental do agente `Socc`.
    - Ajustar a experiência de UX/TUI apenas dentro da implementação atual, sem portar harness legado.
  - v2.0:
    - Integrar threat-intel adapters prioritários e fluxos de IR.
    - Consolidar modo headless/TUI/CLI como runtime unificado do SOCC dentro da stack atual.
    - Evoluir o produto como copiloto SOC sem depender de comandos ou harness herdados do SOCC legado.

- **Technical Risks**:
  - Renomeação ampla pode quebrar scripts, docs, automações e integrações que dependem de `openclaude`.
  - Paths legados como `.openclaude` e referências a `.claude/settings.json` podem gerar confusão operacional ou regressões se a estratégia de migração for incompleta.
  - O reposicionamento de branding sem adaptação real do comportamento do agente pode resultar em “SOCC” apenas cosmético.
  - Misturar domínio SOC com superfícies generalistas sem hierarquia clara pode manter onboarding ambíguo e reduzir confiança do usuário.
  - Reaproveitar acidentalmente comandos ou harness do SOCC legado pode reintroduzir escopo não aprovado e comprometer a coerência da migração.
  - Protocolos e contratos externos, como gRPC e integrações de provider, podem exigir compatibilidade transitória durante a renomeação.
