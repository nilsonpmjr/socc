#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const PACKAGE_ROOT = path.dirname(SCRIPT_DIR);
const isWindows = process.platform === "win32";

function parseArgs(argv) {
  const options = {
    home: process.env.SOCC_HOME || path.join(os.homedir(), ".socc"),
    python: process.env.SOCC_BOOTSTRAP_PYTHON || "",
    force: false,
    probe: false,
    skipDeps: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--home") {
      options.home = argv[index + 1] || options.home;
      index += 1;
    } else if (arg === "--python") {
      options.python = argv[index + 1] || "";
      index += 1;
    } else if (arg === "--force") {
      options.force = true;
    } else if (arg === "--probe") {
      options.probe = true;
    } else if (arg === "--skip-deps") {
      options.skipDeps = true;
    } else if (arg === "--help" || arg === "-h") {
      process.stdout.write(
        [
          "SOCC npm bootstrap",
          "",
          "Uso:",
          "  node scripts/bootstrap-python.mjs [--home PATH] [--python PATH] [--force] [--probe] [--skip-deps]",
        ].join("\n") + "\n",
      );
      process.exit(0);
    }
  }
  return options;
}

function prependPathList(currentValue, extraValue) {
  if (!currentValue) {
    return extraValue;
  }
  const parts = currentValue.split(path.delimiter);
  if (parts.includes(extraValue)) {
    return currentValue;
  }
  return [extraValue, ...parts].join(path.delimiter);
}

function cliEnv(home) {
  return {
    ...process.env,
    SOCC_HOME: home,
    SOCC_PROJECT_ROOT: process.env.SOCC_PROJECT_ROOT || PACKAGE_ROOT,
    PYTHONPATH: prependPathList(process.env.PYTHONPATH || "", PACKAGE_ROOT),
  };
}

function candidatePythons(explicitPython, runtimeHome) {
  const candidates = [];
  if (explicitPython) {
    candidates.push(explicitPython);
  }
  if (process.env.SOCC_PYTHON) {
    candidates.push(process.env.SOCC_PYTHON);
  }
  if (isWindows) {
    candidates.push(
      path.join(runtimeHome, "venv", "Scripts", "python.exe"),
      "py",
      "python",
      "python3",
    );
  } else {
    candidates.push(
      path.join(runtimeHome, "venv", "bin", "python"),
      "python3",
      "python",
    );
  }
  return [...new Set(candidates)];
}

function canRunPython(candidate, home) {
  if (path.isAbsolute(candidate) && !fs.existsSync(candidate)) {
    return false;
  }
  const args = candidate === "py" ? ["-3", "-c", "print('ok')"] : ["-c", "print('ok')"];
  const result = spawnSync(candidate, args, {
    env: cliEnv(home),
    stdio: "ignore",
  });
  return result.status === 0;
}

function pickPython(explicitPython, home) {
  for (const candidate of candidatePythons(explicitPython, home)) {
    if (canRunPython(candidate, home)) {
      return candidate;
    }
  }
  return "";
}

function runPython(pythonBin, args, home, allowFailure = false) {
  const finalArgs = pythonBin === "py" ? ["-3", ...args] : args;
  const result = spawnSync(pythonBin, finalArgs, {
    env: cliEnv(home),
    stdio: "inherit",
  });
  if (!allowFailure && result.status !== 0) {
    process.exit(result.status ?? 1);
  }
  return result;
}

function runPip(pythonBin, pipArgs, home, allowFailure = false) {
  return runPython(pythonBin, ["-m", "pip", ...pipArgs], home, allowFailure);
}

const options = parseArgs(process.argv.slice(2));
const runtimeHome = path.resolve(options.home);
const pythonBin = pickPython(options.python, runtimeHome);

if (!pythonBin) {
  process.stderr.write("Python não encontrado para bootstrap npm do SOCC.\n");
  process.exit(1);
}

fs.mkdirSync(runtimeHome, { recursive: true });

const bootstrapScript = [
  "from pathlib import Path",
  "import sys",
  `sys.path.insert(0, ${JSON.stringify(PACKAGE_ROOT)})`,
  "from socc.cli.installer import bootstrap_runtime",
  `bootstrap_runtime(Path(${JSON.stringify(runtimeHome)}), force=${options.force ? "True" : "False"}, layout='package')`,
].join(";");

runPython(pythonBin, ["-c", bootstrapScript], runtimeHome);

const venvPython = isWindows
  ? path.join(runtimeHome, "venv", "Scripts", "python.exe")
  : path.join(runtimeHome, "venv", "bin", "python");

if (!fs.existsSync(venvPython)) {
  runPython(pythonBin, ["-m", "venv", path.join(runtimeHome, "venv")], runtimeHome);
}

runPip(venvPython, ["install", "--disable-pip-version-check", "--retries", "0", "--timeout", "3", "--upgrade", "pip", "setuptools", "wheel"], runtimeHome, true);

const installArgs = [
  "install",
  "--disable-pip-version-check",
  "--retries",
  "0",
  "--timeout",
  "3",
  "--no-build-isolation",
];
if (options.skipDeps) {
  installArgs.push("--no-deps");
}
installArgs.push(PACKAGE_ROOT);

let installResult = runPip(venvPython, installArgs, runtimeHome, true);
if (installResult.status !== 0 && !options.skipDeps) {
  installResult = runPip(
    venvPython,
    [
      "install",
      "--disable-pip-version-check",
      "--retries",
      "0",
      "--timeout",
      "3",
      "--no-build-isolation",
      "--no-deps",
      PACKAGE_ROOT,
    ],
    runtimeHome,
    true,
  );
}

if (installResult.status !== 0) {
  process.stderr.write("Falha ao instalar o pacote Python do SOCC no venv local.\n");
  process.exit(installResult.status ?? 1);
}

// Garantir InquirerPy para CLI interativa (setas, toggle, autocomplete)
runPip(venvPython, ["install", "--disable-pip-version-check", "--retries", "0", "--timeout", "3", "InquirerPy>=0.3.4"], runtimeHome, true);

const onboardArgs = ["-m", "socc.cli.main", "onboard", "--home", runtimeHome];
if (options.force) {
  onboardArgs.push("--force");
}
if (options.probe) {
  onboardArgs.push("--probe");
}
runPython(venvPython, onboardArgs, runtimeHome);

process.stdout.write(
  [
    "",
    "SOCC npm bootstrap concluído.",
    `Runtime: ${runtimeHome}`,
    `Python: ${venvPython}`,
    `Launcher: ${path.join(runtimeHome, "bin", "socc")}`,
  ].join("\n") + "\n",
);
