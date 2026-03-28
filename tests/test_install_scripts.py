"""
Valida scripts de instalacao one-shot inspirados no fluxo do OpenClaw.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from socc.cli.installer import write_cli_launcher

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


tmpdir = tempfile.TemporaryDirectory()
runtime_root = Path(tmpdir.name) / ".socc-test"

try:
    install_script = ROOT / "install.sh"
    install_cli_script = ROOT / "install-cli.sh"
    check("install_sh_exists", install_script.exists(), str(install_script))
    check("install_cli_sh_exists", install_cli_script.exists(), str(install_cli_script))

    bash_n_install = subprocess.run(
        ["bash", "-n", str(install_script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    check("install_sh_syntax", bash_n_install.returncode == 0, bash_n_install.stderr.strip())

    bash_n_install_cli = subprocess.run(
        ["bash", "-n", str(install_cli_script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    check("install_cli_sh_syntax", bash_n_install_cli.returncode == 0, bash_n_install_cli.stderr.strip())

    help_run = subprocess.run(
        ["bash", str(install_script), "--help"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    check("install_sh_help_exit", help_run.returncode == 0, help_run.stderr.strip())
    check("install_sh_help_text", "SOCC install.sh" in help_run.stdout)

    launcher = write_cli_launcher(runtime_root, python_executable="/usr/bin/python3", force=True)
    launcher_content = launcher.read_text(encoding="utf-8")
    check("install_launcher_created", launcher.exists(), str(launcher))
    check("install_launcher_python", 'SOCC_PYTHON' in launcher_content and 'socc.cli.main' in launcher_content)
    check("install_launcher_project_root", "SOCC_PROJECT_ROOT" in launcher_content and "PYTHONPATH" in launcher_content)
except Exception as exc:
    check("install_scripts_flow", False, str(exc))
finally:
    tmpdir.cleanup()


print(f"\n{'='*60}")
print(f"SOCC Runtime — Install Scripts  ({len(resultados)} checks)")
print("=" * 60)
falhas = [(n, d) for s, n, d in resultados if s == FAIL]
aprovados = len(resultados) - len(falhas)
print(f"  Aprovados : {aprovados}/{len(resultados)}")
print(f"  Falhas    : {len(falhas)}/{len(resultados)}")
print()
for nome, detalhe in falhas:
    extra = f" — {detalhe}" if detalhe else ""
    print(f"  FALHA: {nome}{extra}")
if not falhas:
    print("  Todos os checks passaram.")
print()

sys.exit(1 if falhas else 0)
