const vscode = require('vscode');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const {
  chooseLaunchWorkspace,
  describeProviderState,
  findExistingProfilePath,
  findCommandPath,
  isPathInsideWorkspace,
  parseProfileFile,
  resolveCommandCheckPath,
} = require('./state');
const { buildControlCenterViewModel } = require('./presentation');

const SOCC_REPO_URL = 'https://github.com/nilsonpmjr/socc';
const SOCC_SETUP_URL = 'https://github.com/nilsonpmjr/socc/blob/main/README.md#quick-start';
const PRIMARY_PROFILE_FILE_NAME = '.socc-profile.json';
const PRIMARY_CONFIG_SECTION = 'socc';
const LEGACY_CONFIG_SECTION = 'openclaude';
const PRIMARY_VIEW_CONTAINER = 'socc';
const PRIMARY_VIEW_ID = 'socc.controlCenter';

function getExtensionSetting(key, fallback) {
  const primary = vscode.workspace.getConfiguration(PRIMARY_CONFIG_SECTION).get(key);
  if (primary !== undefined) {
    return primary;
  }
  return vscode.workspace.getConfiguration(LEGACY_CONFIG_SECTION).get(key, fallback);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function isCommandAvailable(command, launchCwd) {
  return Boolean(findCommandPath(command, { cwd: launchCwd }));
}

function getExecutableFromCommand(command) {
  const normalized = String(command || '').trim();
  if (!normalized) {
    return '';
  }

  const doubleQuotedMatch = normalized.match(/^"([^"]+)"/);
  if (doubleQuotedMatch) {
    return doubleQuotedMatch[1];
  }

  const singleQuotedMatch = normalized.match(/^'([^']+)'/);
  if (singleQuotedMatch) {
    return singleQuotedMatch[1];
  }

  return normalized.split(/\s+/)[0];
}

function getWorkspacePaths() {
  return (vscode.workspace.workspaceFolders || []).map(folder => folder.uri.fsPath);
}

function getActiveWorkspacePath() {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.uri.scheme !== 'file') {
    return null;
  }

  const workspaceFolder = vscode.workspace.getWorkspaceFolder(editor.document.uri);
  return workspaceFolder ? workspaceFolder.uri.fsPath : null;
}

function getActiveFilePath() {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.uri.scheme !== 'file') {
    return null;
  }

  return editor.document.uri.fsPath || null;
}

function resolveLaunchTargets({ activeFilePath, workspacePath, workspaceSourceLabel, executable } = {}) {
  const activeFileDirectory = isPathInsideWorkspace(activeFilePath, workspacePath)
    ? path.dirname(activeFilePath)
    : null;
  const normalizedExecutable = String(executable || '').trim();
  const commandPath = normalizedExecutable
    ? resolveCommandCheckPath(normalizedExecutable, workspacePath)
    : null;
  const relativeCommandRequiresWorkspaceRoot = Boolean(
    workspacePath && commandPath && !path.isAbsolute(normalizedExecutable),
  );

  if (relativeCommandRequiresWorkspaceRoot) {
    return {
      projectAwareCwd: workspacePath,
      projectAwareCwdLabel: workspacePath,
      projectAwareSourceLabel: 'workspace root (required by relative launch command)',
      workspaceRootCwd: workspacePath,
      workspaceRootCwdLabel: workspacePath,
      launchActionsShareTarget: true,
      launchActionsShareTargetReason: 'relative-launch-command',
    };
  }

  if (activeFileDirectory) {
    return {
      projectAwareCwd: activeFileDirectory,
      projectAwareCwdLabel: activeFileDirectory,
      projectAwareSourceLabel: 'active file directory',
      workspaceRootCwd: workspacePath || null,
      workspaceRootCwdLabel: workspacePath || 'No workspace open',
      launchActionsShareTarget: false,
      launchActionsShareTargetReason: null,
    };
  }

  if (workspacePath) {
    return {
      projectAwareCwd: workspacePath,
      projectAwareCwdLabel: workspacePath,
      projectAwareSourceLabel: workspaceSourceLabel || 'workspace root',
      workspaceRootCwd: workspacePath,
      workspaceRootCwdLabel: workspacePath,
      launchActionsShareTarget: true,
      launchActionsShareTargetReason: null,
    };
  }

  return {
    projectAwareCwd: null,
    projectAwareCwdLabel: 'VS Code default terminal cwd',
    projectAwareSourceLabel: 'VS Code default terminal cwd',
    workspaceRootCwd: null,
    workspaceRootCwdLabel: 'No workspace open',
    launchActionsShareTarget: false,
    launchActionsShareTargetReason: null,
  };
}

function resolveLaunchWorkspace() {
  return chooseLaunchWorkspace({
    activeWorkspacePath: getActiveWorkspacePath(),
    workspacePaths: getWorkspacePaths(),
  });
}

function getWorkspaceSourceLabel(source) {
  switch (source) {
    case 'active-workspace':
      return 'active editor workspace';
    case 'first-workspace':
      return 'first workspace folder';
    default:
      return 'no workspace open';
  }
}

function getProviderSourceLabel(source) {
  switch (source) {
    case 'profile':
      return 'saved profile';
    case 'env':
      return 'environment';
    case 'shim':
      return 'launch setting';
    default:
      return 'unknown';
  }
}

function readWorkspaceProfile(profilePath) {
  if (!profilePath || !fs.existsSync(profilePath)) {
    return {
      profile: null,
      statusLabel: 'Missing',
        statusHint: `${PRIMARY_PROFILE_FILE_NAME} not found in the workspace root`,
        filePath: null,
      };
  }

  try {
    const raw = fs.readFileSync(profilePath, 'utf8');
    const profile = parseProfileFile(raw);
    if (!profile) {
      return {
        profile: null,
        statusLabel: 'Invalid',
        statusHint: `${profilePath} has invalid JSON or an unsupported profile`,
        filePath: profilePath,
      };
    }

    return {
      profile,
      statusLabel: 'Found',
      statusHint: profilePath,
      filePath: profilePath,
    };
  } catch (error) {
    return {
      profile: null,
      statusLabel: 'Unreadable',
      statusHint: `${profilePath} (${error instanceof Error ? error.message : 'read failed'})`,
      filePath: profilePath,
    };
  }
}

async function collectControlCenterState() {
  const launchCommand = getExtensionSetting('launchCommand', 'socc');
  const terminalName = getExtensionSetting('terminalName', 'SOCC');
  const shimEnabled = getExtensionSetting('useOpenAIShim', false);
  const executable = getExecutableFromCommand(launchCommand);
  const launchWorkspace = resolveLaunchWorkspace();
  const workspaceFolder = launchWorkspace.workspacePath;
  const workspaceSourceLabel = getWorkspaceSourceLabel(launchWorkspace.source);
  const launchTargets = resolveLaunchTargets({
    activeFilePath: getActiveFilePath(),
    workspacePath: workspaceFolder,
    workspaceSourceLabel,
    executable,
  });
  const installed = await isCommandAvailable(executable, launchTargets.projectAwareCwd);
  const profilePath = findExistingProfilePath(workspaceFolder);

  const profileState = workspaceFolder
    ? readWorkspaceProfile(profilePath)
    : {
        profile: null,
        statusLabel: 'No workspace',
        statusHint: 'Open a workspace folder to detect a saved profile',
        filePath: null,
      };

  const providerState = describeProviderState({
    shimEnabled,
    env: process.env,
    profile: profileState.profile,
  });

  return {
    installed,
    executable,
    launchCommand,
    terminalName,
    shimEnabled,
    workspaceFolder,
    workspaceSourceLabel,
    launchCwd: launchTargets.projectAwareCwd,
    launchCwdLabel: launchTargets.projectAwareCwdLabel,
    launchCwdSourceLabel: launchTargets.projectAwareSourceLabel,
    workspaceRootCwd: launchTargets.workspaceRootCwd,
    workspaceRootCwdLabel: launchTargets.workspaceRootCwdLabel,
    launchActionsShareTarget: launchTargets.launchActionsShareTarget,
    launchActionsShareTargetReason: launchTargets.launchActionsShareTargetReason,
    canLaunchInWorkspaceRoot: Boolean(workspaceFolder),
    profileStatusLabel: profileState.statusLabel,
    profileStatusHint: profileState.statusHint,
    workspaceProfilePath: profileState.filePath,
    providerState,
    providerSourceLabel: getProviderSourceLabel(providerState.source),
  };
}

async function launchSocc(options = {}) {
  const { requireWorkspace = false } = options;
  const launchCommand = getExtensionSetting('launchCommand', 'socc');
  const terminalName = getExtensionSetting('terminalName', 'SOCC');
  const shimEnabled = getExtensionSetting('useOpenAIShim', false);
  const executable = getExecutableFromCommand(launchCommand);
  const launchWorkspace = resolveLaunchWorkspace();

  if (requireWorkspace && !launchWorkspace.workspacePath) {
    await vscode.window.showWarningMessage(
      'Open a workspace folder before using Launch in Workspace Root.',
    );
    return;
  }

  const launchTargets = resolveLaunchTargets({
    activeFilePath: getActiveFilePath(),
    workspacePath: launchWorkspace.workspacePath,
    workspaceSourceLabel: getWorkspaceSourceLabel(launchWorkspace.source),
    executable,
  });
  const targetCwd = requireWorkspace
    ? launchTargets.workspaceRootCwd
    : launchTargets.projectAwareCwd;
  const installed = await isCommandAvailable(executable, targetCwd);

  if (!installed) {
    const action = await vscode.window.showErrorMessage(
      `SOCC command not found: ${executable}. Install it with: npm install -g socc`,
      'Open Setup Guide',
      'Open Repository',
    );

    if (action === 'Open Setup Guide') {
      await vscode.env.openExternal(vscode.Uri.parse(SOCC_SETUP_URL));
    } else if (action === 'Open Repository') {
      await vscode.env.openExternal(vscode.Uri.parse(SOCC_REPO_URL));
    }

    return;
  }

  const env = {};
  if (shimEnabled) {
    env.CLAUDE_CODE_USE_OPENAI = '1';
  }

  const terminalOptions = {
    name: terminalName,
    env,
  };

  if (targetCwd) {
    terminalOptions.cwd = targetCwd;
  }

  const terminal = vscode.window.createTerminal(terminalOptions);
  terminal.show(true);
  terminal.sendText(launchCommand, true);
}

async function openWorkspaceProfile() {
  const state = await collectControlCenterState();

  if (!state.workspaceProfilePath) {
    await vscode.window.showInformationMessage(
      `No ${PRIMARY_PROFILE_FILE_NAME} file was found for the current workspace.`,
    );
    return;
  }

  const document = await vscode.workspace.openTextDocument(
    vscode.Uri.file(state.workspaceProfilePath),
  );
  await vscode.window.showTextDocument(document, { preview: false });
}

function getToneClass(tone) {
  switch (tone) {
    case 'accent':
      return 'tone-accent';
    case 'positive':
      return 'tone-positive';
    case 'warning':
      return 'tone-warning';
    case 'critical':
      return 'tone-critical';
    default:
      return 'tone-neutral';
  }
}

function renderHeaderBadge(badge) {
  return `<div class="rail-pill ${getToneClass(badge.tone)}" title="${escapeHtml(badge.label)}: ${escapeHtml(badge.value)}">
    <span class="rail-label">${escapeHtml(badge.label)}</span>
    <span class="rail-value">${escapeHtml(badge.value)}</span>
  </div>`;
}

function renderSummaryCard(card) {
  const detail = card.detail || '';
  return `<section class="summary-card" aria-label="${escapeHtml(card.label)}">
    <div class="summary-label">${escapeHtml(card.label)}</div>
    <div class="summary-value" title="${escapeHtml(card.value)}">${escapeHtml(card.value)}</div>
    ${detail ? `<div class="summary-detail" title="${escapeHtml(detail)}">${escapeHtml(detail)}</div>` : ''}
  </section>`;
}

function renderDetailRow(row) {
  return `<div class="detail-row ${getToneClass(row.tone)}">
    <div class="detail-label">${escapeHtml(row.label)}</div>
    <div class="detail-summary" title="${escapeHtml(row.summary)}">${escapeHtml(row.summary)}</div>
    ${row.detail ? `<div class="detail-meta" title="${escapeHtml(row.detail)}">${escapeHtml(row.detail)}</div>` : ''}
  </div>`;
}

function renderDetailSection(section) {
  const sectionId = `section-${String(section.title || 'section').toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
  return `<section class="detail-module" aria-labelledby="${escapeHtml(sectionId)}">
    <h2 class="module-title" id="${escapeHtml(sectionId)}">${escapeHtml(section.title)}</h2>
    <div class="detail-list">${section.rows.map(renderDetailRow).join('')}</div>
  </section>`;
}

function renderActionButton(action, variant = 'secondary') {
  return `<button class="action-button ${variant}" id="${escapeHtml(action.id)}" type="button" ${action.disabled ? 'disabled aria-disabled="true"' : ''}>
    <span class="action-label">${escapeHtml(action.label)}</span>
    <span class="action-detail">${escapeHtml(action.detail)}</span>
  </button>`;
}

function renderProfileEmptyState(detail) {
  return `<div class="action-empty" role="status" aria-live="polite">
    <div class="action-empty-title">No workspace profile yet</div>
    <div class="action-empty-detail">${escapeHtml(detail)}</div>
  </div>`;
}

function getPrimaryLaunchActionDetail(status) {
  if (status.launchActionsShareTargetReason === 'relative-launch-command' && status.launchCwd) {
    return `Project-aware launch is anchored to the workspace root by the relative command · ${status.launchCwdLabel}`;
  }

  if (status.launchCwd && status.launchCwdSourceLabel === 'active file directory') {
    return `Starts beside the active file · ${status.launchCwdLabel}`;
  }

  if (status.launchCwd) {
    return `Project-aware launch. Currently resolves to ${status.launchCwdSourceLabel} · ${status.launchCwdLabel}`;
  }

  return 'Project-aware launch. Uses the VS Code default terminal cwd';
}

function getWorkspaceRootActionDetail(status, fallbackDetail) {
  if (!status.canLaunchInWorkspaceRoot) {
    return fallbackDetail;
  }

  if (status.launchActionsShareTargetReason === 'relative-launch-command') {
    return `Same workspace-root target as Launch SOCC because the relative command resolves from the workspace root · ${status.workspaceRootCwdLabel}`;
  }

  return `Always starts at the workspace root · ${status.workspaceRootCwdLabel}`;
}

function getRenderableViewModel(status) {
  const viewModel = buildControlCenterViewModel(status);
  const summaryCards = viewModel.summaryCards.map(card => {
    if (card.key !== 'launchCwd' || card.detail) {
      return card;
    }

    return {
      ...card,
      detail: status.launchCwdSourceLabel || '',
    };
  });

  return {
    ...viewModel,
    summaryCards,
    actions: {
      ...viewModel.actions,
      primary: {
        ...viewModel.actions.primary,
        detail: getPrimaryLaunchActionDetail(status),
      },
      launchRoot: {
        ...viewModel.actions.launchRoot,
        detail: getWorkspaceRootActionDetail(status, viewModel.actions.launchRoot.detail),
      },
    },
  };
}

function renderControlCenterHtml(status, options = {}) {
  const nonce = options.nonce || crypto.randomBytes(16).toString('base64');
  const platform = options.platform || process.platform;
  const viewModel = getRenderableViewModel(status);
  const profileActionOrEmpty = viewModel.actions.openProfile
    ? renderActionButton(viewModel.actions.openProfile)
    : renderProfileEmptyState(status.profileStatusHint || 'Open a workspace folder to detect a saved profile');

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <style>
    :root {
      --oc-bg: #030712;
      --oc-panel: #08111f;
      --oc-panel-strong: #0b172a;
      --oc-panel-soft: #10203a;
      --oc-border: #274567;
      --oc-border-soft: rgba(147, 197, 253, 0.16);
      --oc-text: #e2efff;
      --oc-text-dim: #b9d2ee;
      --oc-text-soft: #86a8cd;
      --oc-accent: #3b82f6;
      --oc-accent-bright: #60a5fa;
      --oc-accent-soft: rgba(96, 165, 250, 0.18);
      --oc-positive: #4ade80;
      --oc-warning: #93c5fd;
      --oc-critical: #f87171;
      --oc-focus: #bfdbfe;
    }
    * {
      box-sizing: border-box;
    }
    h1, h2, p {
      margin: 0;
    }
    html, body {
      margin: 0;
      min-height: 100%;
    }
    body {
      padding: 16px;
      font-family: var(--vscode-font-family, "Segoe UI", sans-serif);
      color: var(--oc-text);
      background:
        radial-gradient(circle at top right, rgba(96, 165, 250, 0.18), transparent 34%),
        radial-gradient(circle at 20% 0%, rgba(59, 130, 246, 0.16), transparent 28%),
        linear-gradient(180deg, #06101f, #030712 58%, #06101f);
      line-height: 1.45;
    }
    button {
      font: inherit;
    }
    .shell {
      position: relative;
      overflow: hidden;
      border: 1px solid var(--oc-border-soft);
      border-radius: 20px;
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.02), transparent 16%),
        linear-gradient(180deg, rgba(8, 17, 31, 0.98), rgba(3, 7, 18, 0.98));
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.03);
    }
    .shell::before {
      content: "";
      position: absolute;
      inset: 0 0 auto;
      height: 2px;
      background: linear-gradient(90deg, #93c5fd, #60a5fa, #3b82f6, #1d4ed8);
      opacity: 0.95;
    }
    .signal-gradient {
      background: linear-gradient(90deg, #93c5fd, #60a5fa, #3b82f6, #1d4ed8);
    }
    .frame {
      display: grid;
      gap: 18px;
      padding: 18px;
    }
    .hero {
      display: grid;
      gap: 14px;
      padding: 18px;
      border-radius: 16px;
      background:
        linear-gradient(135deg, rgba(96, 165, 250, 0.08), rgba(59, 130, 246, 0.03) 55%, transparent),
        var(--oc-panel);
      border: 1px solid var(--oc-border-soft);
    }
    .hero-top {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
    }
    .brand {
      display: grid;
      gap: 6px;
      min-width: 0;
    }
    .eyebrow {
      font-size: 11px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--oc-text-soft);
    }
    .wordmark {
      font-size: 24px;
      line-height: 1;
      font-weight: 700;
      letter-spacing: -0.03em;
      color: var(--oc-text);
    }
    .wordmark-accent {
      color: var(--oc-accent-bright);
    }
    .headline {
      display: grid;
      gap: 4px;
      max-width: 44ch;
    }
    .headline-title {
      font-size: 15px;
      font-weight: 600;
      color: var(--oc-text);
    }
    .headline-subtitle {
      font-size: 12px;
      color: var(--oc-text-dim);
    }
    .status-rail {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      justify-content: flex-end;
      flex: 1 1 250px;
    }
    .rail-pill {
      display: grid;
      gap: 2px;
      min-width: 94px;
      padding: 8px 10px;
      border-radius: 999px;
      border: 1px solid var(--oc-border-soft);
      background: rgba(255, 255, 255, 0.02);
    }
    .rail-label {
      font-size: 10px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--oc-text-soft);
    }
    .rail-value {
      font-size: 12px;
      font-weight: 700;
      color: var(--oc-text);
    }
    .refresh-button {
      border: 1px solid rgba(96, 165, 250, 0.28);
      border-radius: 999px;
      padding: 8px 12px;
      background: rgba(96, 165, 250, 0.08);
      color: var(--oc-text-dim);
      cursor: pointer;
      white-space: nowrap;
    }
    .summary-grid {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    }
    .summary-card {
      display: grid;
      gap: 6px;
      min-width: 0;
      padding: 14px;
      border-radius: 14px;
      background: var(--oc-panel-strong);
      border: 1px solid var(--oc-border-soft);
    }
    .summary-label,
    .detail-label,
    .module-title,
    .action-section-title,
    .support-title {
      font-size: 10px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--oc-text-soft);
    }
    .summary-value,
    .detail-summary {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 13px;
      font-weight: 600;
      color: var(--oc-text);
    }
    .summary-detail,
    .detail-meta,
    .action-detail,
    .action-empty-detail,
    .support-copy,
    .footer-note {
      font-size: 12px;
      color: var(--oc-text-dim);
    }
    .modules {
      display: grid;
      gap: 14px;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    }
    .detail-module,
    .support-card {
      display: grid;
      gap: 12px;
      padding: 16px;
      border-radius: 16px;
      background: var(--oc-panel);
      border: 1px solid var(--oc-border-soft);
    }
    .detail-list,
    .action-stack,
    .support-stack {
      display: grid;
      gap: 10px;
    }
    .detail-row {
      display: grid;
      gap: 4px;
      min-width: 0;
      padding: 12px;
      border-radius: 12px;
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid rgba(220, 195, 170, 0.08);
    }
    .actions-layout {
      display: grid;
      gap: 14px;
      grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr);
      align-items: start;
    }
    .action-panel {
      display: grid;
      gap: 12px;
      padding: 16px;
      border-radius: 16px;
      background: var(--oc-panel);
      border: 1px solid var(--oc-border-soft);
    }
    .action-button {
      width: 100%;
      display: grid;
      gap: 4px;
      padding: 14px;
      text-align: left;
      border-radius: 14px;
      border: 1px solid rgba(220, 195, 170, 0.14);
      background: rgba(255, 255, 255, 0.02);
      color: var(--oc-text);
      cursor: pointer;
      transition: border-color 140ms ease, transform 140ms ease, background 140ms ease, box-shadow 140ms ease;
    }
    .action-button.primary {
      border-color: rgba(96, 165, 250, 0.44);
      background:
        linear-gradient(135deg, rgba(147, 197, 253, 0.22), rgba(59, 130, 246, 0.14) 58%, rgba(29, 78, 216, 0.14)),
        #10203a;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
    }
    .action-button.secondary:hover:enabled,
    .action-button.primary:hover:enabled,
    .refresh-button:hover {
      border-color: rgba(96, 165, 250, 0.48);
      transform: translateY(-1px);
      background-color: rgba(96, 165, 250, 0.1);
    }
    .action-button:disabled {
      cursor: not-allowed;
      opacity: 0.58;
      transform: none;
    }
    .action-label,
    .action-empty-title,
    .support-link-label {
      font-size: 13px;
      font-weight: 700;
      color: var(--oc-text);
    }
    .action-empty {
      display: grid;
      gap: 4px;
      padding: 14px;
      border-radius: 14px;
      border: 1px dashed rgba(220, 195, 170, 0.16);
      background: rgba(255, 255, 255, 0.015);
    }
    .support-link {
      width: 100%;
      display: grid;
      gap: 4px;
      padding: 12px 0;
      border: 0;
      border-top: 1px solid rgba(220, 195, 170, 0.08);
      background: transparent;
      color: inherit;
      cursor: pointer;
      text-align: left;
    }
    .support-link:first-of-type {
      border-top: 0;
      padding-top: 0;
    }
    .tone-positive .rail-value,
    .tone-positive .detail-summary {
      color: var(--oc-positive);
    }
    .tone-warning .rail-value,
    .tone-warning .detail-summary {
      color: var(--oc-warning);
    }
    .tone-critical .rail-value,
    .tone-critical .detail-summary {
      color: var(--oc-critical);
    }
    .tone-accent .rail-value,
    .tone-accent .detail-summary {
      color: var(--oc-accent-bright);
    }
    .action-button:focus-visible,
    .support-link:focus-visible,
    .refresh-button:focus-visible {
      outline: 2px solid var(--oc-focus);
      outline-offset: 2px;
      box-shadow: 0 0 0 4px rgba(255, 211, 161, 0.16);
    }
    code {
      padding: 1px 6px;
      border-radius: 999px;
      border: 1px solid rgba(240, 148, 100, 0.18);
      background: rgba(240, 148, 100, 0.08);
      color: var(--oc-accent-bright);
      font-family: var(--vscode-editor-font-family, Consolas, monospace);
      font-size: 11px;
    }
    .footer-note {
      padding-top: 2px;
    }
    @media (max-width: 720px) {
      body {
        padding: 12px;
      }
      .frame,
      .hero {
        padding: 14px;
      }
      .actions-layout {
        grid-template-columns: 1fr;
      }
      .status-rail {
        justify-content: flex-start;
      }
      .rail-pill {
        min-width: 0;
      }
    }
  </style>
</head>
<body>
  <main class="shell" aria-labelledby="control-center-title">
    <div class="frame">
      <header class="hero">
        <div class="hero-top">
          <div class="brand">
            <div class="eyebrow">${escapeHtml(viewModel.header.eyebrow)}</div>
            <div class="wordmark" aria-label="SOCC wordmark">SOCC</div>
            <div class="headline">
              <h1 class="headline-title" id="control-center-title">${escapeHtml(viewModel.header.title)}</h1>
              <p class="headline-subtitle">${escapeHtml(viewModel.header.subtitle)}</p>
            </div>
          </div>
          <div class="status-rail" role="group" aria-label="Runtime, provider, and profile status">
            ${viewModel.headerBadges.map(renderHeaderBadge).join('')}
            <button class="refresh-button" id="refresh" type="button">Refresh</button>
          </div>
        </div>
        <section class="summary-grid" aria-label="Current launch summary">
          ${viewModel.summaryCards.map(renderSummaryCard).join('')}
        </section>
      </header>

      <section class="modules" aria-label="Control center details">
        ${viewModel.detailSections.map(renderDetailSection).join('')}
      </section>

      <section class="actions-layout" aria-label="Control center actions">
        <section class="action-panel" aria-labelledby="actions-title">
          <h2 class="action-section-title" id="actions-title">Launch & Project</h2>
          ${renderActionButton(viewModel.actions.primary, 'primary')}
          <div class="action-stack">
            ${renderActionButton(viewModel.actions.launchRoot)}
            ${profileActionOrEmpty}
          </div>
        </section>

        <section class="support-card" aria-labelledby="quick-links-title">
          <h2 class="support-title" id="quick-links-title">Quick Links</h2>
          <div class="support-copy">Settings and workspace status stay in view here. Reference links stay secondary.</div>
          <div class="support-stack">
            <button class="support-link" id="setup" type="button">
              <span class="support-link-label">Open Setup Guide</span>
              <span class="summary-detail">Jump to install and provider setup docs.</span>
            </button>
            <button class="support-link" id="repo" type="button">
              <span class="support-link-label">Open Repository</span>
              <span class="summary-detail">Browse the SOCC repository.</span>
            </button>
            <button class="support-link" id="commands" type="button">
              <span class="support-link-label">Open Command Palette</span>
              <span class="summary-detail">Access VS Code and SOCC commands quickly.</span>
            </button>
          </div>
        </section>
      </section>

      <p class="footer-note">
        Quick trigger: use <code>${escapeHtml(platform === 'darwin' ? 'Cmd+Shift+P' : 'Ctrl+Shift+P')}</code> for the command palette, then refresh this panel after workspace or profile changes.
      </p>
    </div>
  </main>

  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    document.getElementById('launch').addEventListener('click', () => vscode.postMessage({ type: 'launch' }));
    document.getElementById('launchRoot').addEventListener('click', () => vscode.postMessage({ type: 'launchRoot' }));
    document.getElementById('repo').addEventListener('click', () => vscode.postMessage({ type: 'repo' }));
    document.getElementById('setup').addEventListener('click', () => vscode.postMessage({ type: 'setup' }));
    document.getElementById('commands').addEventListener('click', () => vscode.postMessage({ type: 'commands' }));
    document.getElementById('refresh').addEventListener('click', () => vscode.postMessage({ type: 'refresh' }));

    const profileButton = document.getElementById('openProfile');
    if (profileButton) {
      profileButton.addEventListener('click', () => vscode.postMessage({ type: 'openProfile' }));
    }
  </script>
</body>
</html>`;
}

class SoccControlCenterProvider {
  constructor() {
    this.webviewView = null;
  }

  async resolveWebviewView(webviewView) {
    this.webviewView = webviewView;
    webviewView.webview.options = { enableScripts: true };

    webviewView.onDidDispose(() => {
      if (this.webviewView === webviewView) {
        this.webviewView = null;
      }
    });

    webviewView.webview.onDidReceiveMessage(async message => {
      switch (message?.type) {
        case 'launch':
          await launchSocc();
          break;
        case 'launchRoot':
          await launchSocc({ requireWorkspace: true });
          break;
        case 'openProfile':
          await openWorkspaceProfile();
          break;
        case 'repo':
          await vscode.env.openExternal(vscode.Uri.parse(SOCC_REPO_URL));
          break;
        case 'setup':
          await vscode.env.openExternal(vscode.Uri.parse(SOCC_SETUP_URL));
          break;
        case 'commands':
          await vscode.commands.executeCommand('workbench.action.showCommands');
          break;
        case 'refresh':
        default:
          break;
      }

      await this.refresh();
    });

    await this.refresh();
  }

  async refresh() {
    if (!this.webviewView) {
      return;
    }

    try {
      const status = await collectControlCenterState();
      this.webviewView.webview.html = this.getHtml(status);
    } catch (error) {
      this.webviewView.webview.html = this.getErrorHtml(error);
    }
  }

  getErrorHtml(error) {
    const nonce = crypto.randomBytes(16).toString('base64');
    const message =
      error instanceof Error ? error.message : 'Unknown Control Center error';

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <style>
    body {
      font-family: var(--vscode-font-family);
      padding: 16px;
      color: var(--vscode-foreground);
      background: var(--vscode-sideBar-background);
    }
    .panel {
      border: 1px solid var(--vscode-errorForeground);
      border-radius: 8px;
      padding: 14px;
      background: color-mix(in srgb, var(--vscode-sideBar-background) 88%, black);
    }
    .title {
      color: var(--vscode-errorForeground);
      font-weight: 700;
      margin-bottom: 8px;
    }
    .message {
      color: var(--vscode-descriptionForeground);
      margin-bottom: 12px;
      line-height: 1.5;
    }
    button {
      border: 1px solid var(--vscode-button-border, transparent);
      background: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
      border-radius: 6px;
      padding: 8px 10px;
      cursor: pointer;
    }
  </style>
</head>
<body>
  <div class="panel">
    <div class="title">Control Center Error</div>
    <div class="message">${escapeHtml(message)}</div>
    <button id="refresh">Refresh</button>
  </div>
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    document.getElementById('refresh').addEventListener('click', () => {
      vscode.postMessage({ type: 'refresh' });
    });
  </script>
</body>
</html>`;
  }

  getHtml(status) {
    const nonce = crypto.randomBytes(16).toString('base64');
    return renderControlCenterHtml(status, { nonce, platform: process.platform });
  }
}

/**
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
  const provider = new SoccControlCenterProvider();
  const refreshProvider = () => {
    void provider.refresh();
  };

  const startCommand = vscode.commands.registerCommand('socc.start', async () => {
    await launchSocc();
  });
  const legacyStartCommand = vscode.commands.registerCommand('openclaude.start', async () => {
    await launchSocc();
  });

  const startInWorkspaceRootCommand = vscode.commands.registerCommand(
    'socc.startInWorkspaceRoot',
    async () => {
      await launchSocc({ requireWorkspace: true });
    },
  );
  const legacyStartInWorkspaceRootCommand = vscode.commands.registerCommand(
    'openclaude.startInWorkspaceRoot',
    async () => {
      await launchSocc({ requireWorkspace: true });
    },
  );

  const openDocsCommand = vscode.commands.registerCommand('socc.openDocs', async () => {
    await vscode.env.openExternal(vscode.Uri.parse(SOCC_REPO_URL));
  });
  const legacyOpenDocsCommand = vscode.commands.registerCommand('openclaude.openDocs', async () => {
    await vscode.env.openExternal(vscode.Uri.parse(SOCC_REPO_URL));
  });

  const openSetupDocsCommand = vscode.commands.registerCommand(
    'socc.openSetupDocs',
    async () => {
      await vscode.env.openExternal(vscode.Uri.parse(SOCC_SETUP_URL));
    },
  );
  const legacyOpenSetupDocsCommand = vscode.commands.registerCommand(
    'openclaude.openSetupDocs',
    async () => {
      await vscode.env.openExternal(vscode.Uri.parse(SOCC_SETUP_URL));
    },
  );

  const openWorkspaceProfileCommand = vscode.commands.registerCommand(
    'socc.openWorkspaceProfile',
    async () => {
      await openWorkspaceProfile();
    },
  );
  const legacyOpenWorkspaceProfileCommand = vscode.commands.registerCommand(
    'openclaude.openWorkspaceProfile',
    async () => {
      await openWorkspaceProfile();
    },
  );

  const openUiCommand = vscode.commands.registerCommand('socc.openControlCenter', async () => {
    await vscode.commands.executeCommand(`workbench.view.extension.${PRIMARY_VIEW_CONTAINER}`);
  });
  const legacyOpenUiCommand = vscode.commands.registerCommand('openclaude.openControlCenter', async () => {
    await vscode.commands.executeCommand(`workbench.view.extension.${PRIMARY_VIEW_CONTAINER}`);
  });

  const providerDisposable = vscode.window.registerWebviewViewProvider(
    PRIMARY_VIEW_ID,
    provider,
  );

  const profileWatcher = vscode.workspace.createFileSystemWatcher(`**/{.socc-profile.json,.openclaude-profile.json}`);

  context.subscriptions.push(
    startCommand,
    legacyStartCommand,
    startInWorkspaceRootCommand,
    legacyStartInWorkspaceRootCommand,
    openDocsCommand,
    legacyOpenDocsCommand,
    openSetupDocsCommand,
    legacyOpenSetupDocsCommand,
    openWorkspaceProfileCommand,
    legacyOpenWorkspaceProfileCommand,
    openUiCommand,
    legacyOpenUiCommand,
    providerDisposable,
    profileWatcher,
    vscode.workspace.onDidChangeConfiguration(event => {
      if (event.affectsConfiguration(PRIMARY_CONFIG_SECTION) || event.affectsConfiguration(LEGACY_CONFIG_SECTION)) {
        refreshProvider();
      }
    }),
    vscode.workspace.onDidChangeWorkspaceFolders(refreshProvider),
    vscode.window.onDidChangeActiveTextEditor(refreshProvider),
    profileWatcher.onDidCreate(refreshProvider),
    profileWatcher.onDidChange(refreshProvider),
    profileWatcher.onDidDelete(refreshProvider),
  );
}

function deactivate() {}

module.exports = {
  activate,
  deactivate,
  SoccControlCenterProvider,
  renderControlCenterHtml,
  resolveLaunchTargets,
};
