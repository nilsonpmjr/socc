#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PACKAGE_ROOT = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const runtimeHome = process.env.SOCC_HOME || path.join(os.homedir(), ".socc");
const isWindows = process.platform === "win32";

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

function cliEnv() {
  return {
    ...process.env,
    SOCC_HOME: runtimeHome,
    SOCC_PROJECT_ROOT: process.env.SOCC_PROJECT_ROOT || PACKAGE_ROOT,
    PYTHONPATH: prependPathList(process.env.PYTHONPATH || "", PACKAGE_ROOT),
  };
}

function runtimeVenvPython(homePath) {
  if (isWindows) {
    return path.join(homePath, "venv", "Scripts", "python.exe");
  }
  return path.join(homePath, "venv", "bin", "python");
}

function systemPythonCandidates() {
  const candidates = [];
  if (process.env.SOCC_PYTHON) {
    candidates.push(process.env.SOCC_PYTHON);
  }
  candidates.push(runtimeVenvPython(runtimeHome));
  if (process.env.SOCC_BOOTSTRAP_PYTHON) {
    candidates.push(process.env.SOCC_BOOTSTRAP_PYTHON);
  }
  if (isWindows) {
    candidates.push("py", "python", "python3");
  } else {
    candidates.push("python3", "python");
  }
  return [...new Set(candidates)];
}

function canImportRuntime(pythonCandidate) {
  if (path.isAbsolute(pythonCandidate) && !fs.existsSync(pythonCandidate)) {
    return false;
  }
  const probeArgs = pythonCandidate === "py" ? ["-3", "-c", "import socc.cli.main"] : ["-c", "import socc.cli.main"];
  const result = spawnSync(pythonCandidate, probeArgs, {
    env: cliEnv(),
    stdio: "ignore",
  });
  return result.status === 0;
}

function findPython() {
  for (const candidate of systemPythonCandidates()) {
    if (canImportRuntime(candidate)) {
      return candidate;
    }
  }
  return "";
}

function bootstrapPython() {
  const scriptPath = path.join(PACKAGE_ROOT, "scripts", "bootstrap-python.mjs");
  const result = spawnSync(process.execPath, [scriptPath, "--home", runtimeHome], {
    env: cliEnv(),
    stdio: "inherit",
  });
  return result.status === 0;
}

function printBootstrapHint() {
  const lines = [
    "SOCC npm wrapper could not find a working Python runtime.",
    "Try one of these commands:",
    "  npm run setup",
    "  node scripts/bootstrap-python.mjs",
    "  SOCC_BOOTSTRAP_PYTHON=/path/to/python3 node socc.mjs setup",
  ];
  process.stderr.write(`${lines.join("\n")}\n`);
}

if (args[0] === "setup" || args[0] === "bootstrap-python") {
  const scriptPath = path.join(PACKAGE_ROOT, "scripts", "bootstrap-python.mjs");
  const result = spawnSync(process.execPath, [scriptPath, ...args.slice(1)], {
    env: cliEnv(),
    stdio: "inherit",
  });
  process.exit(result.status ?? 1);
}

let pythonBin = findPython();
if (!pythonBin && process.env.SOCC_NPM_AUTO_BOOTSTRAP !== "0") {
  if (bootstrapPython()) {
    pythonBin = findPython();
  }
}

if (!pythonBin) {
  printBootstrapHint();
  process.exit(1);
}

const pythonArgs = pythonBin === "py" ? ["-3", "-m", "socc.cli.main", ...args] : ["-m", "socc.cli.main", ...args];
const result = spawnSync(pythonBin, pythonArgs, {
  env: cliEnv(),
  stdio: "inherit",
});

if (typeof result.status === "number") {
  process.exit(result.status);
}

process.exit(1);
