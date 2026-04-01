# scripts/checks/

Scripts de verificação standalone (não são testes pytest).

Executar individualmente:

```bash
python scripts/checks/check_runtime_bootstrap.py
python scripts/checks/check_vantage_gateway.py
# ...
```

Ou todos de uma vez:

```bash
for f in scripts/checks/check_*.py; do
    echo "=== $f ==="; python "$f" 2>&1 | tail -2
done
```

## Por que não estão em `tests/`?

Estes scripts foram escritos antes da adoção de pytest e usam um
padrão próprio de `check()` + `sys.exit()`. Funcionam como
smoke-tests contra módulos legados (`soc_copilot/`).

Os testes pytest reais vivem em `tests/` e cobrem os módulos
modernos em `socc/`.
