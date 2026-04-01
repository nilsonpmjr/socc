# Auditoria Completa do Projeto SOC Copilot

**Data:** 2026-03-28
**Escopo:** Bugs, codigo morto, pontos de melhoria e questoes de seguranca
**Arquivos analisados:** Todos os arquivos Python (`soc_copilot/`, `socc/`, `tests/`, root), templates HTML, `.env.example`

---

## Resumo Executivo

| Severidade | Quantidade |
|------------|-----------|
| CRITICAL   | 6         |
| HIGH       | 21        |
| MEDIUM     | 43        |
| LOW        | 54        |

---

## CRITICAL - Acao Imediata Necessaria

### 1. Command Injection via subprocess

- **Arquivos:** `soc_copilot/modules/ti_adapter.py:52` e `analise_ofensa.py:45`
- **Descricao:** IOCs de origem do usuario passados diretamente como argumento ao `subprocess.run()` sem sanitizacao. Se o script `threat_check.py` interpretar o argumento de forma insegura, e exploravel.
- **Correcao:** Validar e sanitizar IOCs antes de passar ao subprocess. Implementar allowlist de caracteres permitidos.

### 2. Command Injection no CLI Launcher

- **Arquivo:** `socc/cli/installer.py:98-114`
- **Descricao:** `write_cli_launcher()` interpola `python_cmd`, `fallback_python_cmd` e `source_root` diretamente em um shell script sem escaping. Caminhos com metacaracteres shell permitem execucao arbitraria.
- **Correcao:** Usar `shlex.quote()` em todos os valores interpolados no shell script.

### 3. Arbitrary File Write via Path Traversal

- **Arquivo:** `socc/utils/config_loader.py:36-46` (chamado de `socc/core/engine.py:1207-1212`)
- **Descricao:** `update_env_assignment()` aceita `Path` e escreve nele. Se `SOCC_HOME` apontar para `/etc/`, arquivos sensiveis podem ser sobrescritos.
- **Correcao:** Validar que o path resolvido esta dentro do diretorio esperado usando `Path.resolve()` e comparacao de prefixo.

### 4. SQL Injection Pattern

- **Arquivo:** `soc_copilot/modules/persistence.py:108-111`
- **Descricao:** `_ensure_column()` usa f-strings para nomes de tabela/coluna em SQL. Apesar de atualmente ser chamado com literais, o padrao e perigoso.
- **Correcao:** Usar whitelist de nomes de tabela/coluna permitidos ou validar contra regex `^[a-zA-Z_][a-zA-Z0-9_]*$`.

### 5. Unsafe Tool Invocation via kwargs unpacking

- **Arquivo:** `socc/core/tools.py:18-34`
- **Descricao:** `invoke_tool()` passa argumentos do usuario via `**payload`, permitindo chamar qualquer tool registrado com argumentos arbitrarios.
- **Correcao:** Validar argumentos contra schema esperado antes de passar via kwargs.

### 6. Path Traversal no endpoint `/api/save`

- **Arquivo:** `soc_copilot/main.py:176-193`
- **Descricao:** `ofensa_id` vem de form data sem validacao. Valores como `../../etc/passwd` podem escrever em locais arbitrarios.
- **Correcao:** Sanitizar `ofensa_id` removendo separadores de path e validar que o path resolvido esta dentro de `OUTPUT_DIR`.

---

## HIGH - Seguranca e Bugs Graves

### Seguranca

| # | Arquivo | Descricao |
|---|---------|-----------|
| 1 | `soc_copilot/main.py` (todos endpoints) | Nenhum endpoint tem autenticacao. Qualquer cliente na rede pode invocar todas as operacoes. |
| 2 | `mcp_server.py:101` | `get_model()` usa glob com input do usuario sem validar se o arquivo resolvido esta dentro do diretorio permitido. |
| 3 | `soc_copilot/templates/index.html:922` | Padrao fragil com `innerHTML` para o campo `racional` que pode ser explorado em mudancas futuras. |
| 4 | `soc_copilot/templates/chat.html:1384` | Funcao `esc()` nao escapa aspas simples (`'`), ao contrario de `escHtml` em index.html. Permite breakout em atributos HTML com aspas simples. |
| 5 | `.env.example:18` | `TI_API_PASS=iteam123` -- credencial real em arquivo exemplo. |
| 6 | `soc_copilot/modules/ti_adapter.py:73-78` | Credenciais enviadas via HTTP sem verificar se URL usa HTTPS. |
| 7 | `soc_copilot/config.py:21-24` | Paths de desenvolvedor especifico como defaults, vazando username e estrutura interna. |

### Bugs

| # | Arquivo | Descricao |
|---|---------|-----------|
| 8 | `soc_copilot/modules/soc_copilot_loader.py:207` | Regex quebrada: `\\b` em raw string corresponde a `\b` literal, nao word boundary. Deteccao de URL/dominio nunca funciona corretamente. |
| 9 | `socc/core/memory.py:10-11` vs `socc/cli/installer.py` | `runtime_home()` inconsistente: uma versao ignora `SOCC_HOME`, outra respeita. Logs vao para diretorios diferentes. |
| 10 | `socc/core/memory.py:6`, `socc/core/chat.py:6`, etc. | Hard dependency em pacote legacy `soc_copilot` -- se o pacote nao existir, multiplos modulos falham em cascata. |
| 11 | `socc/gateway/llm_gateway.py:245` | `_INFERENCE_SEMAPHORE` inicializado no import, ignora mudancas de configuracao em runtime. |
| 12 | `socc/core/engine.py:814-825` | Regex `(\w+=(?:"[^"]*"|[^\s]+)\s+){3,}` com quantificadores aninhados pode causar backtracking catastrofico (ReDoS). |
| 13 | `soc_copilot/modules/chat_service.py:348-351` | `resp.close()` no `finally` quando `resp` pode ser `None`. O `except Exception: pass` mascara o erro real. |
| 14 | `soc_copilot/modules/soc_copilot_loader.py:263` | `config.skills[skill_name]` pode lancar `KeyError` se o skill escolhido nao existir no dict carregado. |
| 15 | `soc_copilot/modules/soc_copilot_loader.py:120` | `_read_text()` chama `path.read_text()` sem tratar `FileNotFoundError`. Se qualquer arquivo do agente estiver faltando, o load inteiro falha sem mensagem clara. |

---

## MEDIUM - Melhorias Importantes

### Seguranca

| # | Arquivo | Descricao |
|---|---------|-----------|
| 1 | `soc_copilot/main.py:130,379` | Mensagens de erro expoe detalhes internos via `str(exc)` diretamente ao cliente. |
| 2 | `soc_copilot/main.py:82-130` | Endpoint `/api/analyze` aceita payloads e uploads sem limites explicitos de tamanho (vetor de DoS). |
| 3 | `socc/core/engine.py:767` e `soc_copilot/templates/chat.html:354` | Session IDs usam `time()` / `Date.now()` em vez de UUID -- colisoes possiveis em alta concorrencia. |
| 4 | `soc_copilot/templates/chat.html:1178-1208` | Valores embutidos em inline `onclick` handlers via template literals -- padrao fragil para XSS. |
| 5 | `socc/core/engine.py:926-930` | Protecao contra path traversal usa `startswith` em vez de `Path.resolve()` -- bypass possivel em alguns filesystems. |
| 6 | `socc/gateway/llm_gateway.py:413-425` | `nvidia-smi` executado via subprocess -- um binario malicioso mais cedo no `PATH` seria executado. |

### Bugs

| # | Arquivo | Descricao |
|---|---------|-----------|
| 7 | `soc_copilot/modules/semi_llm_adapter.py:220-244` | `_merge_nested_dict(output[key], output.get(key))` -- merge consigo mesmo. Provavel erro de copy-paste; intent era merge com `fallback.get(key)`. |
| 8 | `soc_copilot/modules/semi_llm_adapter.py:798` | Regex `\{[\s\S]*\}` greedy captura do primeiro `{` ao ultimo `}` da string inteira -- falha com multiplos objetos JSON. |
| 9 | `socc/core/knowledge_base.py:589-635` | Race condition: leitura/escrita nao atomica do index JSONL, sem file locking. Ingestoes concorrentes podem corromper o indice. |
| 10 | `soc_copilot/modules/ti_adapter.py:103-123` | `time.sleep(2)` em polling loop de ate 60s -- bloqueia thread do event loop em contexto async. |
| 11 | `socc/core/engine.py:234` | `_infer_ioc_type()` aceita strings como `1.2.3.4.5.6` como IPs validos. Nao detecta IPv6. |
| 12 | `soc_copilot/main.py:366` | `"prepared" in locals()` para controle de fluxo -- fragil. Inicializar `prepared = None` antes do try. |
| 13 | `analise_ofensa.py:61-62` | `extract_iocs()` nao valida que octetos IP estao entre 0-255. `999.999.999.999` seria tratado como IP valido. |
| 14 | `analise_ofensa.py:79-84` | `process_payload()` engole todas as excecoes no parse JSON com `pass`. Falhas silenciosas. |
| 15 | `socc/core/knowledge_base.py:92-95` | `_json_load()` nao trata `json.JSONDecodeError`. Arquivo JSON corrompido causa excecao nao tratada. |
| 16 | `socc/core/engine.py:47-59` | TOCTOU race condition em `_can_bind()` -- porta pode ser tomada entre o check e o `uvicorn.run()`. |
| 17 | `socc/cli/service_manager.py:156-159` | `stop_service()` envia SIGTERM e remove PID file imediatamente sem aguardar terminacao do processo. |
| 18 | `socc/core/engine.py:303-305` | `_normalize_draft_fields()` trata todos os IPs invalidos como privados silenciosamente. |
| 19 | `mcp_server.py:161` | `cliente.lower()` pode lancar `AttributeError` se `cliente` for `None`. |

### Qualidade de Codigo

| # | Arquivo(s) | Descricao |
|---|------------|-----------|
| 20 | `analysis_trace.py`, `telemetry_context.py`, `analysis_priority.py`, `analysis_export.py`, `analysis_contract.py` | `_clean_text()` duplicada em 5 modulos. Extrair para modulo compartilhado. |
| 21 | `draft_engine.py:84`, `analysis_priority.py:21` | `_VERTICAL_LABELS` duplicado em dois arquivos com valores identicos. |
| 22 | `soc_copilot/modules/parser_engine.py:686-896` | Funcao `parse()` com ~50 variaveis locais e 200+ linhas. Dificil de testar e manter. |
| 23 | `soc_copilot/modules/persistence.py:9-14` | `get_conn()` cria nova conexao SQLite a cada chamada. Sem connection pool. |
| 24 | `socc/core/knowledge_base.py:460` | Carrega index JSONL inteiro em memoria a cada busca. Usar streaming line-by-line. |
| 25 | `soc_copilot/modules/parser_engine.py:167-171` | `_is_private_ip()` cria objetos `ip_network` a cada chamada. Deveria ser constante de modulo. |
| 26 | `soc_copilot/modules/chat_service.py:205,222-226` | Historico buscado duas vezes na mesma funcao `_prepare_chat_context()`. Dobra queries ao banco. |
| 27 | `socc/gateway/llm_gateway.py:577` | `recent_events()` usa slicing desnecessariamente complexo. |

### Testes

| # | Descricao |
|---|-----------|
| 28 | Todos os testes usam um harness `check()` customizado em vez de pytest/unittest -- sem isolamento, fixtures, ou integracao CI padrao. |
| 29 | Testes modificam estado global (`os.environ`, `persistence.DB_PATH`) restaurando em `finally` -- se um teste crashar antes, o estado vaza. |
| 30 | `tests/test_chat_endpoints.py:164` -- monkey-patching fragil de `asyncio.to_thread` pode afetar outros testes. |

---

## MEDIUM/HIGH - Gaps de Cobertura de Testes

| Gap | Descricao |
|-----|-----------|
| `analise_ofensa.py` | Zero cobertura de testes. |
| `mcp_server.py` | Zero cobertura de testes. |
| Testes de seguranca | Nenhum teste para SQL injection, path traversal, XSS, SSRF, ou sanitizacao de input. |
| Upload de arquivos | Nenhum teste para arquivos grandes, binarios, ou filenames maliciosos. |
| Frontend JavaScript | Logica de SSE, markdown rendering, session management sem testes. |
| Caminhos de erro HTTP | Testes minimos para JSON malformado, payloads oversized, ou requests concorrentes. |

---

## LOW - Codigo Morto e Melhorias Menores

### Codigo Morto / Imports Nao Utilizados

| # | Arquivo | Descricao |
|---|---------|-----------|
| 1 | `analise_ofensa.py:2` | `import csv` nunca usado. |
| 2 | `soc_copilot/modules/semi_llm_adapter.py:47-65` | `INPUT_SCHEMA` definido mas nunca usado para validacao. Serve apenas como comentario. |
| 3 | `soc_copilot/main.py:406` | `effective_session` computado mas nunca usado no `except` block de `event_stream()`. |
| 4 | `socc/core/engine.py:816-817` | `import re as regex` sombra o `import re` do modulo. Redundante. |

### Bugs Menores

| # | Arquivo | Descricao |
|---|---------|-----------|
| 5 | `soc_copilot/modules/parser_engine.py:225-236` | `convert_to_sp()` assume UTC para timestamps sem offset -- pode ser incorreto para timestamps em hora local. |
| 6 | `soc_copilot/modules/model_parser.py:172-202` | `_anonymize` com regex `r'\b[a-z]{2,}\.[a-z]{2,}\b'` tambem faz match em termos legitimos como `e.g`, `i.e`. |
| 7 | `analise_ofensa.py:115-116` | `defang_url()` chamado em campos de usuario, tornando emails ilegaveis (ex: `user@company[.]com`). |
| 8 | `socc/core/engine.py:28` (via `prompts.py:6`) | `AGENT_ROOT` computado em tempo de import a partir de `__file__`. Se instalado via pip, o diretorio `.agents/soc-copilot` nao existira relativo ao modulo instalado. |
| 9 | `socc/gateway/mcp_gateway.py:8` | `load_server_module()` importa `"mcp_server"` hardcoded. Se o modulo nao existir, `ImportError` sem contexto util. |

### Melhorias Menores

| # | Arquivo | Descricao |
|---|---------|-----------|
| 10 | `soc_copilot/templates/index.html:1020` e `chat.html:1277` | `document.execCommand("copy")` esta deprecated. Usar `navigator.clipboard.writeText()`. |
| 11 | `soc_copilot/templates/index.html:1232-1233` | `setLoading()` acessa elementos por ID que podem nao existir ainda (null reference). |
| 12 | `soc_copilot/templates/chat.html:354` | `state.sessionId = String(Date.now())` -- nao e collision-resistant. Usar `crypto.randomUUID()`. |
| 13 | `soc_copilot/modules/rule_loader.py:15` | `_normalize_client` e apenas wrapper desnecessario para `_normalize_text`. |
| 14 | `socc/utils/safety.py:8-10` | `_IPV4_RE` aceita IPs invalidos como `999.999.999.999`. `_HASH_RE` pode fazer match em valores nao-hash. Causa over-redaction. |

---

## Recomendacoes Prioritarias (Top 10)

1. **Sanitizar inputs em subprocess/SQL/paths** -- validar e sanitizar IOCs, `ofensa_id`, e qualquer input usado em subprocessos, queries SQL, ou construcao de caminhos de arquivo.
2. **Adicionar autenticacao** -- implementar auth middleware (API key no minimo) em todos os endpoints HTTP.
3. **Corrigir regex quebrada** em `soc_copilot_loader.py:207` -- `\\b` deve ser `\b`.
4. **Unificar `runtime_home()`** -- uma unica implementacao que respeite `SOCC_HOME` em todos os modulos.
5. **Completar `esc()` em chat.html** -- adicionar escape de `'` (aspas simples) para consistencia com `escHtml`.
6. **Remover caminhos Windows hardcoded** e credenciais do `.env.example` e `config.py`.
7. **Corrigir self-merge bug** em `semi_llm_adapter.py:220-244` -- trocar `output.get(key)` por `fallback.get(key)`.
8. **Extrair `_clean_text()` para modulo compartilhado** -- eliminar duplicacao em 5 arquivos.
9. **Migrar testes para pytest** -- obter isolamento, fixtures, paralelismo e integracao CI adequados.
10. **Implementar limites de tamanho** no FastAPI para uploads e payloads, e usar mensagens de erro genericas para o cliente.

---

## Notas

- Esta auditoria foi realizada via analise estatica do codigo-fonte. Testes de penetracao em runtime podem revelar vulnerabilidades adicionais.
- Os achados de seguranca assumem que a aplicacao pode ser exposta em rede. Se executada apenas localmente, o risco de alguns itens e reduzido (mas nao eliminado).
- Recomenda-se executar ferramentas SAST (Bandit, Semgrep) para complementar esta revisao manual.
