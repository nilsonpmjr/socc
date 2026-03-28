#!/usr/bin/env python3
"""Cross-platform SOCC installer.

Works on Linux, macOS, and Windows.  Replaces install.sh for environments
where bash is not available.

Usage:
    python install.py [--home PATH] [--python PATH] [--standard]
                      [--skip-deps] [--force] [--probe]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = os.name == "nt"
ROOT_DIR = Path(__file__).resolve().parent


def _find_python() -> str:
    """Find a usable Python interpreter."""
    candidates = ["python3", "python"]
    if IS_WINDOWS:
        candidates = ["py", "python", "python3"]
    for candidate in candidates:
        exe = shutil.which(candidate)
        if exe:
            return exe
    return sys.executable


def _run(cmd: list[str], *, check: bool = True, allow_fail: bool = False) -> int:
    """Run a command, printing it first."""
    print(f"  > {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if check and not allow_fail and result.returncode != 0:
        print(f"  ERRO: comando falhou com código {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)
    return result.returncode


def _venv_python(socc_home: Path) -> str:
    if IS_WINDOWS:
        return str(socc_home / "venv" / "Scripts" / "python.exe")
    return str(socc_home / "venv" / "bin" / "python")


def _venv_pip(socc_home: Path) -> list[str]:
    return [_venv_python(socc_home), "-m", "pip"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Instalador cross-platform do SOCC")
    parser.add_argument("--home", default=os.environ.get("SOCC_HOME", str(Path.home() / ".socc")),
                        help="Diretório do runtime (padrão: ~/.socc)")
    parser.add_argument("--python", default="", help="Interpretador Python a usar")
    parser.add_argument("--standard", action="store_true", help="pip install . em vez de -e .")
    parser.add_argument("--skip-deps", action="store_true", help="Instala com --no-deps")
    parser.add_argument("--force", action="store_true", help="Reexecuta onboarding com --force")
    parser.add_argument("--probe", action="store_true", help="Executa probe do backend")
    args = parser.parse_args()

    socc_home = Path(args.home).expanduser().resolve()
    python_bin = args.python or _find_python()

    print(f"\nSOCC Installer")
    print(f"  OS:      {sys.platform} ({os.name})")
    print(f"  Python:  {python_bin}")
    print(f"  Home:    {socc_home}")
    print(f"  Root:    {ROOT_DIR}")
    print()

    # 1. Bootstrap runtime
    socc_home.mkdir(parents=True, exist_ok=True)
    force_py = "True" if args.force else "False"
    bootstrap_script = (
        f"import sys; sys.path.insert(0, {str(ROOT_DIR)!r}); "
        f"from socc.cli.installer import bootstrap_runtime; "
        f"from pathlib import Path; "
        f"bootstrap_runtime(Path({str(socc_home)!r}), force={force_py})"
    )
    _run([python_bin, "-c", bootstrap_script])

    # 2. Create venv if missing
    venv_py = _venv_python(socc_home)
    if not Path(venv_py).exists():
        print("\n  Criando venv...")
        _run([python_bin, "-m", "venv", str(socc_home / "venv")])

    # 3. Upgrade pip/setuptools
    pip_common = ["--disable-pip-version-check", "--retries", "0", "--timeout", "3"]
    _run([*_venv_pip(socc_home), "install", *pip_common, "--upgrade", "pip", "setuptools", "wheel"],
         allow_fail=True)

    # 4. Install package
    pip_args = ["install", *pip_common, "--no-build-isolation"]
    if args.skip_deps:
        pip_args.append("--no-deps")

    install_target = str(ROOT_DIR)
    if not args.standard:
        pip_args.extend(["-e", install_target])
    else:
        pip_args.append(install_target)

    rc = _run([*_venv_pip(socc_home), *pip_args], allow_fail=True)
    if rc != 0 and not args.skip_deps:
        # Retry without deps
        pip_args_retry = ["install", *pip_common, "--no-build-isolation", "--no-deps"]
        if not args.standard:
            pip_args_retry.extend(["-e", install_target])
        else:
            pip_args_retry.append(install_target)
        rc = _run([*_venv_pip(socc_home), *pip_args_retry], allow_fail=True)

    if rc != 0:
        print("ERRO: Falha ao instalar o pacote SOCC.", file=sys.stderr)
        sys.exit(rc)

    # 5. Install InquirerPy
    _run([*_venv_pip(socc_home), "install", *pip_common, "InquirerPy>=0.3.4"], allow_fail=True)

    # 6. Create PATH shim (platform-specific)
    if IS_WINDOWS:
        _create_windows_path_shim(socc_home)
    else:
        _create_unix_path_shim(socc_home)

    # 7. Run onboard
    onboard_args = [venv_py, "-m", "socc.cli.main", "onboard", "--home", str(socc_home)]
    if args.force:
        onboard_args.append("--force")
    if args.probe:
        onboard_args.append("--probe")

    env = {**os.environ, "SOCC_HOME": str(socc_home), "SOCC_PROJECT_ROOT": str(ROOT_DIR),
           "PYTHONPATH": str(ROOT_DIR) + (os.pathsep + os.environ.get("PYTHONPATH", ""))}
    print("\n  Executando onboard...")
    subprocess.run(onboard_args, env=env)

    # 8. Done
    launcher = socc_home / "bin" / ("socc.cmd" if IS_WINDOWS else "socc")
    print(f"""
SOCC instalado com sucesso.

  Runtime:  {socc_home}
  Python:   {venv_py}
  Launcher: {launcher}
  OS:       {sys.platform}

Próximos passos:
  1. socc doctor --probe
  2. socc serve
""")


def _create_unix_path_shim(socc_home: Path) -> None:
    local_bin = Path.home() / ".local" / "bin"
    try:
        local_bin.mkdir(parents=True, exist_ok=True)
        shim = local_bin / "socc"
        shim.write_text(
            f"#!/usr/bin/env bash\nset -euo pipefail\nexec \"{socc_home}/bin/socc\" \"$@\"\n",
            encoding="utf-8",
        )
        shim.chmod(shim.stat().st_mode | 0o755)
        print(f"  PATH shim: {shim}")
    except OSError as exc:
        print(f"  Aviso: não foi possível criar shim em {local_bin}: {exc}", file=sys.stderr)


def _create_windows_path_shim(socc_home: Path) -> None:
    """Create a shim in a location likely on PATH (or suggest adding to PATH)."""
    # Try user's Scripts dir from the system Python
    scripts_dir = Path(sys.executable).parent / "Scripts"
    if not scripts_dir.exists():
        scripts_dir = Path.home() / ".local" / "bin"

    try:
        scripts_dir.mkdir(parents=True, exist_ok=True)
        shim = scripts_dir / "socc.cmd"
        shim.write_text(
            f"@echo off\r\n\"{socc_home}\\bin\\socc.cmd\" %*\r\n",
            encoding="utf-8",
        )
        print(f"  PATH shim: {shim}")
        if str(scripts_dir) not in os.environ.get("PATH", ""):
            print(f"  Adicione ao PATH: {scripts_dir}")
    except OSError as exc:
        print(f"  Aviso: não foi possível criar shim: {exc}", file=sys.stderr)
        print(f"  Use diretamente: {socc_home}\\bin\\socc.cmd")


if __name__ == "__main__":
    main()
