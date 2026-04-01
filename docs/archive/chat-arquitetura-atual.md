## Arquitetura atual do chat

### Visao geral

O chat do SOCC hoje opera em duas camadas:

- camada web em [soc_copilot/main.py](/home/nilsonpmjr/.gemini/antigravity/scratch/socc/soc_copilot/main.py)
- camada de runtime em [socc/core/engine.py](/home/nilsonpmjr/.gemini/antigravity/scratch/socc/socc/core/engine.py)

A rota raiz `/` redireciona para `/chat`, que é a interface principal atual. A interface antiga de análise/manual segue disponível em `/legacy`.

### Rotas web relevantes

- `GET /`
  Redireciona para `/chat`.
- `GET /chat`
  Entrega a interface principal de chat em [chat.html](/home/nilsonpmjr/.gemini/antigravity/scratch/socc/soc_copilot/templates/chat.html).
- `GET /legacy`
  Entrega a interface antiga em [index.html](/home/nilsonpmjr/.gemini/antigravity/scratch/socc/soc_copilot/templates/index.html).
- `POST /api/chat`
  Fluxo síncrono do chat.
- `POST /api/chat/stream`
  Fluxo SSE do chat.
- `GET /api/chat/sessions`
  Lista sessões persistidas.
- `GET /api/chat/sessions/{session_id}`
  Lista mensagens da sessão.

### Fluxo do chat livre

1. A UI em [chat.html](/home/nilsonpmjr/.gemini/antigravity/scratch/socc/soc_copilot/templates/chat.html) envia para `/api/chat` ou `/api/chat/stream`.
2. A camada web normaliza o corpo via `prepare_chat_submission_inputs()` em [engine.py](/home/nilsonpmjr/.gemini/antigravity/scratch/socc/socc/core/engine.py).
3. O runtime decide se a entrada parece payload ou conversa livre.
4. Para conversa livre, o runtime delega a [socc/core/chat.py](/home/nilsonpmjr/.gemini/antigravity/scratch/socc/socc/core/chat.py), que hoje aponta para [chat_service.py](/home/nilsonpmjr/.gemini/antigravity/scratch/socc/soc_copilot/modules/chat_service.py).
5. O `chat_service` monta contexto de agente, histórico, retrieval lexical local e consulta a LLM quando habilitada.

### Fluxo de payload no chat

1. `chat_submission()` em [engine.py](/home/nilsonpmjr/.gemini/antigravity/scratch/socc/socc/core/engine.py) detecta payload via `looks_like_payload()`.
2. O runtime executa `build_chat_payload_response()`.
3. Esse caminho reaproveita o pipeline estruturado de análise, prioridade, trilha e draft.
4. O resultado final volta para a UI como card analítico.

### Templates e responsabilidades

- [chat.html](/home/nilsonpmjr/.gemini/antigravity/scratch/socc/soc_copilot/templates/chat.html)
  Interface principal de chat, sessões, exportação, feedback e preferências locais.
- [index.html](/home/nilsonpmjr/.gemini/antigravity/scratch/socc/soc_copilot/templates/index.html)
  Interface legada centrada em análise/draft manual.

### Uso atual de MCP

O fluxo principal do chat web não depende de [socc/gateway/mcp_gateway.py](/home/nilsonpmjr/.gemini/antigravity/scratch/socc/socc/gateway/mcp_gateway.py).

O que existe hoje é:

- o chat livre usa `chat_service` e não passa pelo gateway MCP externo
- a análise semi-LLM em [semi_llm_adapter.py](/home/nilsonpmjr/.gemini/antigravity/scratch/socc/soc_copilot/modules/semi_llm_adapter.py) usa ferramentas locais em estilo MCP/tool-calling quando o provider é Ollama
- essas ferramentas são executadas localmente por `_execute_mcp_tool()` e não dependem do `mcp_gateway` externo para o fluxo principal funcionar

Conclusão prática:

- o fluxo principal do chat já está desacoplado do gateway MCP externo
- o uso de MCP hoje é acessório e localizado na análise semi-LLM, como enriquecimento/tool-calling local

### Pontos de atenção

- o contrato HTTP principal do chat já está centralizado no runtime
- a UI principal já é o chat, e a interface antiga ficou preservada apenas como compatibilidade operacional
- regressões comuns desse fluxo agora devem ser cobertas por testes de integração HTTP da camada web
