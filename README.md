# socc

Projeto local de apoio a triagem SOC, parsing de payloads, enriquecimento de IOCs e geração controlada de alertas e notas operacionais.

## Escopo atual

- parsing de entradas em texto, JSON e CSV
- normalização de campos e IOCs
- integração local de Threat Intelligence
- análise estruturada pré-draft
- geração controlada de saídas operacionais
- interface local para análise, revisão, cópia e salvamento
- base inicial para runtime instalável com CLI, gateway e MCP

## Estrutura principal

- `soc_copilot/`: aplicação web atual e módulos do MVP
- `socc/`: pacote instalável com `cli`, `core`, `gateway` e `utils`
- `tests/`: suíte de regressão e casos extremos
- `run.py`: entrypoint compatível com o MVP atual
- `pyproject.toml`: configuração do pacote instalável e do binário `socc`

## Instalação em modo editável

```bash
pip install -e .
```

## Comandos principais

```bash
socc init
socc serve
socc analyze --file caminho/do/payload.txt --json
```

Compatibilidade com o fluxo atual:

```bash
python run.py
```

## Direção arquitetural

O pacote `socc` foi adicionado como camada de runtime para aproximar o projeto de um modelo instalável estilo agent/runtime:

- `socc.cli`: comandos locais como `init`, `serve` e `analyze`
- `socc.core`: wrappers para engine, memória, prompts e ferramentas
- `socc.gateway`: preparação para execução LLM local/remota e integração MCP
- `socc.utils`: carregamento de configuração e parsing utilitário

O projeto continua usando variáveis locais definidas em `.env`, com possibilidade de bootstrap de `~/.socc/.env` via `socc init`.
