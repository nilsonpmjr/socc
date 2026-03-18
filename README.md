# socc

Projeto local de apoio a triagem SOC, parsing de payloads, enriquecimento de IOCs e geração controlada de alertas e notas operacionais.

## Escopo atual

- parsing de entradas em texto, JSON e CSV
- normalização de campos e IOCs
- integração local de Threat Intelligence
- análise estruturada pré-draft
- geração controlada de saídas operacionais
- interface local para análise, revisão, cópia e salvamento

## Estrutura principal

- `soc_copilot/`: aplicação principal
- `tests/`: suíte de regressão e casos extremos
- `run.py`: inicialização local do MVP
- `SOC_Copilot_PRD.md`: PRD do MVP
- `SOC_Copilot_TODO.md`: acompanhamento de fases e entregas

## Execução local

```bash
python run.py
```

O projeto usa variáveis locais definidas em `.env`.
