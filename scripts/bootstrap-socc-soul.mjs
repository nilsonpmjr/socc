import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { existsSync } from 'node:fs'
import { homedir } from 'node:os'
import {
  cp,
  mkdir,
  readFile,
  readdir,
  rm,
  stat,
  writeFile,
} from 'node:fs/promises'
import { dirname, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const SOC_CANONICAL_ROOT = ['socc-canonical', '.agents']
const SOC_COPILOT_DIR = [...SOC_CANONICAL_ROOT, 'soc-copilot']
const RULES_DIR = [...SOC_CANONICAL_ROOT, 'rules']
const WORKFLOWS_DIR = [...SOC_CANONICAL_ROOT, 'workflows']
const GENERATED_DIR = [...SOC_CANONICAL_ROOT, 'generated']

const RUNTIME_ROOT = ['.socc']
const RUNTIME_AGENT_PATH = [...RUNTIME_ROOT, 'agents', 'socc.md']
const RUNTIME_RULES_DIR = [...RUNTIME_ROOT, 'rules']
const RUNTIME_SKILLS_DIR = [...RUNTIME_ROOT, 'skills']
const RUNTIME_REFERENCES_DIR = [...RUNTIME_ROOT, 'references']

const RULE_RUNTIME_FILES = [
  { source: RULES_DIR, file: 'AGENT.md', title: 'Global Behavior Rules' },
  { source: RULES_DIR, file: 'TOOLS.md', title: 'Global Tooling Rules' },
  { source: RULES_DIR, file: 'MEMORY.md', title: 'Persistent Conventions' },
  { source: WORKFLOWS_DIR, file: 'SOP.md', title: 'IOC Handling SOP' },
]

function getWindowsWorkspaceLayout({
  platform = process.platform,
  env = process.env,
  home = homedir(),
} = {}) {
  if (platform !== 'win32') {
    return null
  }

  const userProfile = env.USERPROFILE || env.HOME || home
  const configHome =
    env.SOCC_CONFIG_DIR && env.SOCC_CONFIG_DIR.trim().length > 0
      ? resolve(env.SOCC_CONFIG_DIR)
      : join(userProfile, '.socc')
  const documentsDir = join(userProfile, 'Documents')

  return {
    userProfile,
    configHome,
    documentsDir,
    generatedAlertsDir: join(documentsDir, 'Alertas_Gerados'),
    modelsDir: join(documentsDir, 'Modelos'),
    generatedNotesDir: join(documentsDir, 'Notas_Geradas'),
    trainingDir: join(documentsDir, 'Training'),
  }
}

export async function ensureWindowsWorkspaceLayout(options = {}) {
  const layout = getWindowsWorkspaceLayout(options)
  if (!layout) {
    return null
  }

  await Promise.all([
    mkdir(layout.configHome, { recursive: true }),
    mkdir(layout.generatedAlertsDir, { recursive: true }),
    mkdir(layout.modelsDir, { recursive: true }),
    mkdir(layout.generatedNotesDir, { recursive: true }),
    mkdir(layout.trainingDir, { recursive: true }),
  ])

  return layout
}

function applyWindowsWorkspacePaths(ruleBundle, workspaceLayout) {
  if (!workspaceLayout) {
    return ruleBundle
  }

  const configHomePath = 'USERPROFILE\\.socc'
  const alertsPath = 'USERPROFILE\\Documents\\Alertas_Gerados'
  const modelsPath = 'USERPROFILE\\Documents\\Modelos'
  const notesPath = 'USERPROFILE\\Documents\\Notas_Geradas'
  const trainingPath = 'USERPROFILE\\Documents\\Training'
  const trainingPattern = `${trainingPath}\\Pensamento_Ofensa_*.md`
  const trainingFilePath = `${trainingPath}\\Pensamento_Ofensa_[ID].md`

  const replacements = [
    ['`Modelos\\`', `\`${modelsPath}\``],
    ['`Training\\Pensamento_Ofensa_*.md`', `\`${trainingPattern}\``],
    ['`Training\\Pensamento_Ofensa_[ID].md`', `\`${trainingFilePath}\``],
  ]

  let rewrittenBundle = ruleBundle
  for (const [from, to] of replacements) {
    rewrittenBundle = rewrittenBundle.split(from).join(to)
  }

  return [
    rewrittenBundle.trimEnd(),
    '',
    '## Windows Workspace Paths',
    '',
    '---',
    'trigger: always_on',
    '---',
    '',
    '# Diretórios operacionais no Windows',
    '',
    'No Windows, use estes diretórios como destino oficial dos artefatos do SOCC, sempre sob `USERPROFILE\\Documents`:',
    '',
    `- Configuração do usuário: \`${configHomePath}\``,
    `- Alertas gerados: \`${alertsPath}\``,
    `- Modelos do analista: \`${modelsPath}\``,
    `- Notas geradas: \`${notesPath}\``,
    `- Treinamento: \`${trainingPath}\``,
    '',
    'Regras obrigatórias:',
    '',
    '1. Nunca use a pasta do repositório do SOCC como destino para alertas, notas, modelos ou arquivos de treinamento.',
    `2. Consulte modelos somente em \`${modelsPath}\`.`,
    `3. Salve alertas finais em \`${alertsPath}\`.`,
    `4. Salve notas de encerramento em \`${notesPath}\`.`,
    `5. Salve arquivos de treinamento em \`${trainingPath}\`.`,
    '6. A pasta `.socc` do pacote é a referência final do runtime no Windows; `socc-canonical` não deve ser tratado como diretório operacional.',
    '',
  ].join('\n')
}

function findPackageRoot(startDir) {
  let current = resolve(startDir)

  while (true) {
    if (existsSync(join(current, 'package.json'))) {
      return current
    }

    const parent = dirname(current)
    if (parent === current) {
      throw new Error(`Could not find package root from ${startDir}`)
    }
    current = parent
  }
}

async function readRequiredFile(path) {
  return readFile(path, 'utf8')
}

function hasCanonicalSource(packageRoot) {
  return existsSync(join(packageRoot, ...SOC_COPILOT_DIR, 'identity.md'))
}

function hasPackagedRuntime(packageRoot) {
  return existsSync(join(packageRoot, ...RUNTIME_AGENT_PATH))
}

async function readOptionalFile(path) {
  if (!existsSync(path)) {
    return ''
  }
  return readFile(path, 'utf8')
}

function sha256(content) {
  return createHash('sha256').update(content).digest('hex')
}

async function fileMetadata(path) {
  const content = await readFile(path, 'utf8')
  const stats = await stat(path)
  return {
    path,
    sha256: sha256(content),
    mtimeMs: stats.mtimeMs,
  }
}

async function collectFileList(rootDir) {
  if (!existsSync(rootDir)) {
    return []
  }

  const results = []

  async function walk(currentDir) {
    const entries = await readdir(currentDir, { withFileTypes: true })
    entries.sort((a, b) => a.name.localeCompare(b.name))

    for (const entry of entries) {
      const fullPath = join(currentDir, entry.name)
      if (entry.isDirectory()) {
        await walk(fullPath)
      } else if (entry.isFile()) {
        results.push(fullPath)
      }
    }
  }

  await walk(rootDir)
  return results
}

async function replaceDirectory(sourceDir, targetDir) {
  if (!existsSync(sourceDir)) {
    throw new Error(`Required source directory not found: ${sourceDir}`)
  }

  await rm(targetDir, { recursive: true, force: true })
  await mkdir(dirname(targetDir), { recursive: true })
  await cp(sourceDir, targetDir, { recursive: true })
}

function composeRuleBundle(sections) {
  return [
    '# SOCC Business Rules',
    '',
    '<!-- Generated from socc-canonical/.agents/rules and workflows. -->',
    '',
    ...sections.flatMap(section => [
      `## ${section.title}`,
      '',
      section.content.trim(),
      '',
    ]),
  ].join('\n')
}

export function composeSoccAgentPrompt(parts) {
  return `---
name: socc
description: Security operations analyst for SOC triage, threat intelligence, and incident response support.
model: inherit
---

<!--
Generated from socc-canonical/.agents/soc-copilot.
Do not edit this file directly. Edit the canonical source files and rerun the soul bootstrap.
-->

# Canonical Identity

${parts.identity.trim()}

# Core Soul

${parts.soul.trim()}

# User Context

${parts.user.trim()}

# Orchestration Rules

${parts.agents.trim()}

# Tooling Contract

${parts.tools.trim()}

# Stable Memory

${parts.memory.trim()}

# Skill Selection

${parts.skills.trim()}

# Top-Level Skill Contract

${parts.skill.trim()}
`
}

async function buildRuntimeRules(packageRoot, options = {}) {
  const sections = []
  for (const section of RULE_RUNTIME_FILES) {
    const sourcePath = join(packageRoot, ...section.source, section.file)
    const content = await readOptionalFile(sourcePath)
    if (!content.trim()) {
      continue
    }
    sections.push({
      title: section.title,
      sourcePath,
      content,
    })
  }

  const runtimeRulesDir = join(packageRoot, ...RUNTIME_RULES_DIR)
  const runtimeRulesPath = join(runtimeRulesDir, 'socc-business-rules.md')
  const workspaceLayout = getWindowsWorkspaceLayout(options)

  await rm(runtimeRulesDir, { recursive: true, force: true })
  await mkdir(runtimeRulesDir, { recursive: true })
  await writeFile(
    runtimeRulesPath,
    applyWindowsWorkspacePaths(composeRuleBundle(sections), workspaceLayout),
    'utf8',
  )

  return {
    runtimeRulesDir,
    runtimeRulesPath,
    sections: await Promise.all(
      sections.map(async section => ({
        title: section.title,
        ...(await fileMetadata(section.sourcePath)),
      })),
    ),
  }
}

async function buildRuntimeReferences(packageRoot) {
  const sourceDir = join(packageRoot, ...SOC_COPILOT_DIR, 'references')
  const targetDir = join(packageRoot, ...RUNTIME_REFERENCES_DIR)

  await rm(targetDir, { recursive: true, force: true })
  if (existsSync(sourceDir)) {
    await mkdir(dirname(targetDir), { recursive: true })
    await cp(sourceDir, targetDir, { recursive: true })
  }

  return {
    runtimeReferencesDir: targetDir,
    referenceFiles: await Promise.all(
      (await collectFileList(targetDir)).map(fileMetadata),
    ),
  }
}

async function discoverSkillNames(skillsRoot) {
  if (!existsSync(skillsRoot)) {
    return []
  }

  const entries = await readdir(skillsRoot, { withFileTypes: true })
  const names = []

  for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
    if (!entry.isDirectory()) {
      continue
    }
    if (existsSync(join(skillsRoot, entry.name, 'SKILL.md'))) {
      names.push(entry.name)
    }
  }

  return names
}

async function buildRuntimeSkills(packageRoot, skillNames = null) {
  const sourceSkillsRoot = join(packageRoot, ...SOC_COPILOT_DIR, 'skills')
  const runtimeSkillsDir = join(packageRoot, ...RUNTIME_SKILLS_DIR)
  const namesToSync = skillNames ?? (await discoverSkillNames(sourceSkillsRoot))

  await rm(runtimeSkillsDir, { recursive: true, force: true })
  await mkdir(runtimeSkillsDir, { recursive: true })

  const copied = []
  for (const skillName of namesToSync) {
    const sourceDir = join(sourceSkillsRoot, skillName)
    if (!existsSync(sourceDir)) {
      throw new Error(`Skill not found in canonical source: ${skillName}`)
    }
    const targetDir = join(runtimeSkillsDir, skillName)
    await cp(sourceDir, targetDir, { recursive: true })
    copied.push({
      name: skillName,
      path: targetDir,
      ...(await fileMetadata(join(sourceDir, 'SKILL.md'))),
    })
  }

  return {
    runtimeSkillsDir,
    runtimeSkills: copied,
  }
}

async function buildManifest({
  packageRoot,
  upstreamRoot,
  generatedAgentPath,
  generatedManifestPath,
  runtimeAgentPath,
  runtimeRulesPath,
  runtimeSkillsDir,
  runtimeReferencesDir,
  runtimeSkills,
}) {
  const toManifestPath = path =>
    relative(packageRoot, path).split(sep).join('/')

  const canonicalRoot = join(packageRoot, ...SOC_COPILOT_DIR)
  const sourceFiles = {
    identity: join(canonicalRoot, 'identity.md'),
    soul: join(canonicalRoot, 'SOUL.md'),
    user: join(canonicalRoot, 'USER.md'),
    agents: join(canonicalRoot, 'AGENTS.md'),
    tools: join(canonicalRoot, 'TOOLS.md'),
    memory: join(canonicalRoot, 'MEMORY.md'),
    skills: join(canonicalRoot, 'skills.md'),
    skill: join(canonicalRoot, 'SKILL.md'),
    rulesAgent: join(packageRoot, ...RULES_DIR, 'AGENT.md'),
    rulesTools: join(packageRoot, ...RULES_DIR, 'TOOLS.md'),
    rulesMemory: join(packageRoot, ...RULES_DIR, 'MEMORY.md'),
    workflowSop: join(packageRoot, ...WORKFLOWS_DIR, 'SOP.md'),
  }

  const sourceBlocks = {}
  for (const [name, path] of Object.entries(sourceFiles)) {
    if (existsSync(path)) {
      const metadata = await fileMetadata(path)
      sourceBlocks[name] = {
        ...metadata,
        path: toManifestPath(metadata.path),
      }
    }
  }

  return {
    generatedAt: new Date().toISOString(),
    sourceRoot: toManifestPath(canonicalRoot),
    upstreamRoot: upstreamRoot || null,
    generatedAgentPath: toManifestPath(generatedAgentPath),
    generatedManifestPath: toManifestPath(generatedManifestPath),
    runtimeAgentPath: toManifestPath(runtimeAgentPath),
    runtimeRulesPath: toManifestPath(runtimeRulesPath),
    runtimeSkillsDir: toManifestPath(runtimeSkillsDir),
    runtimeReferencesDir: toManifestPath(runtimeReferencesDir),
    runtimeSkillNames: runtimeSkills.map(skill => skill.name),
    sourceFiles: Object.fromEntries(
      Object.entries(sourceFiles).map(([name, path]) => [
        name,
        toManifestPath(path),
      ]),
    ),
    sourceBlocks,
    runtimeSkills: runtimeSkills.map(skill => ({
      ...skill,
      path: toManifestPath(skill.path),
    })),
  }
}

export async function syncSoccCanonicalFromUpstream(packageRoot, upstreamRoot) {
  if (!upstreamRoot) {
    throw new Error('upstreamRoot is required for canonical sync')
  }

  const canonicalRoot = join(packageRoot, ...SOC_CANONICAL_ROOT)
  const syncTargets = [
    { source: join(upstreamRoot, 'rules'), target: join(canonicalRoot, 'rules') },
    {
      source: join(upstreamRoot, 'soc-copilot'),
      target: join(canonicalRoot, 'soc-copilot'),
    },
    {
      source: join(upstreamRoot, 'workflows'),
      target: join(canonicalRoot, 'workflows'),
    },
  ]

  await mkdir(canonicalRoot, { recursive: true })
  await Promise.all(syncTargets.map(target => replaceDirectory(target.source, target.target)))

  return {
    upstreamRoot,
    canonicalRoot,
    syncedPaths: syncTargets.map(target => ({
      source: target.source,
      target: target.target,
    })),
  }
}

export async function syncSoccSoul(
  packageRoot,
  {
    upstreamRoot = null,
    skillNames = null,
    platform = process.platform,
    env = process.env,
  } = {},
) {
  await ensureWindowsWorkspaceLayout({ platform, env })

  if (upstreamRoot) {
    await syncSoccCanonicalFromUpstream(packageRoot, upstreamRoot)
  }

  const canonicalRoot = join(packageRoot, ...SOC_COPILOT_DIR)
  const generatedDir = join(packageRoot, ...GENERATED_DIR)
  const runtimeAgentPath = join(packageRoot, ...RUNTIME_AGENT_PATH)
  const generatedAgentPath = join(generatedDir, 'socc-agent.md')
  const generatedManifestPath = join(generatedDir, 'socc-agent-manifest.json')

  const [
    identity,
    soul,
    user,
    agents,
    tools,
    memory,
    skills,
    skill,
  ] = await Promise.all([
    readRequiredFile(join(canonicalRoot, 'identity.md')),
    readRequiredFile(join(canonicalRoot, 'SOUL.md')),
    readRequiredFile(join(canonicalRoot, 'USER.md')),
    readRequiredFile(join(canonicalRoot, 'AGENTS.md')),
    readRequiredFile(join(canonicalRoot, 'TOOLS.md')),
    readRequiredFile(join(canonicalRoot, 'MEMORY.md')),
    readRequiredFile(join(canonicalRoot, 'skills.md')),
    readRequiredFile(join(canonicalRoot, 'SKILL.md')),
  ])

  const prompt = composeSoccAgentPrompt({
    identity,
    soul,
    user,
    agents,
    tools,
    memory,
    skills,
    skill,
  })

  await mkdir(dirname(runtimeAgentPath), { recursive: true })
  await mkdir(generatedDir, { recursive: true })

  await Promise.all([
    writeFile(generatedAgentPath, prompt, 'utf8'),
    writeFile(runtimeAgentPath, prompt, 'utf8'),
  ])

  const runtimeRules = await buildRuntimeRules(packageRoot, {
    platform,
    env,
  })
  const runtimeReferences = await buildRuntimeReferences(packageRoot)
  const runtimeSkills = await buildRuntimeSkills(packageRoot, skillNames)

  const manifest = await buildManifest({
    packageRoot,
    upstreamRoot,
    generatedAgentPath,
    generatedManifestPath,
    runtimeAgentPath,
    runtimeRulesPath: runtimeRules.runtimeRulesPath,
    runtimeSkillsDir: runtimeSkills.runtimeSkillsDir,
    runtimeReferencesDir: runtimeReferences.runtimeReferencesDir,
    runtimeSkills: runtimeSkills.runtimeSkills,
  })

  await writeFile(
    generatedManifestPath,
    JSON.stringify(manifest, null, 2),
    'utf8',
  )

  return {
    generatedAgentPath,
    generatedManifestPath,
    runtimeAgentPath,
    runtimeRulesPath: runtimeRules.runtimeRulesPath,
    runtimeSkillsDir: runtimeSkills.runtimeSkillsDir,
    runtimeReferencesDir: runtimeReferences.runtimeReferencesDir,
    upstreamRoot,
    runtimeSkillNames: runtimeSkills.runtimeSkills.map(skill => skill.name),
  }
}

function parseArgs(argv) {
  const args = [...argv]
  let upstreamRoot =
    process.env.SOCC_AGENTS_UPSTREAM?.trim() || null

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index]
    if (arg === '--upstream') {
      upstreamRoot = args[index + 1] ? resolve(args[index + 1]) : null
      index += 1
    }
  }

  return { upstreamRoot }
}

async function main() {
  const scriptDir = dirname(fileURLToPath(import.meta.url))
  const packageRoot = findPackageRoot(scriptDir)
  const { upstreamRoot } = parseArgs(process.argv.slice(2))

  await ensureWindowsWorkspaceLayout()

  if (!upstreamRoot && !hasCanonicalSource(packageRoot)) {
    if (!hasPackagedRuntime(packageRoot)) {
      throw new Error(
        'SOCC canonical source is unavailable and no packaged runtime artifacts were found.',
      )
    }

    console.log(
      'SOCC packaged runtime already contains .socc artifacts; skipping canonical sync.',
    )
    return
  }

  const result = await syncSoccSoul(packageRoot, { upstreamRoot })

  assert.ok(result.generatedAgentPath)
  assert.ok(result.generatedManifestPath)
  assert.ok(result.runtimeAgentPath)
  assert.ok(result.runtimeRulesPath)
  assert.ok(result.runtimeSkillsDir)

  console.log('SOCC soul synced from canonical source.')
  if (result.upstreamRoot) {
    console.log(`Upstream synced: ${result.upstreamRoot}`)
  }
  console.log(`Generated agent: ${result.generatedAgentPath}`)
  console.log(`Manifest: ${result.generatedManifestPath}`)
  console.log(`Runtime agent: ${result.runtimeAgentPath}`)
  console.log(`Runtime rules: ${result.runtimeRulesPath}`)
  console.log(`Runtime skills: ${result.runtimeSkillsDir}`)
}

const isDirectExecution =
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)

if (isDirectExecution) {
  await main()
}
