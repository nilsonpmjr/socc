import assert from 'node:assert/strict'
import { mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

import {
  composeSoccAgentPrompt,
  syncSoccCanonicalFromUpstream,
  syncSoccSoul,
} from './bootstrap-socc-soul.mjs'

const execFileAsync = promisify(execFile)
const bootstrapScriptPath = fileURLToPath(
  new URL('./bootstrap-socc-soul.mjs', import.meta.url),
)

const ALL_TEST_SKILLS = [
  'soc-generalist',
  'payload-triage',
  'phishing-analysis',
  'malware-behavior',
  'suspicious-url',
  'humanizer',
].sort()

test('composeSoccAgentPrompt includes the canonical sections', () => {
  const prompt = composeSoccAgentPrompt({
    identity: '# identity\nidentity text',
    soul: '# soul\nsoul text',
    user: '# user\nuser text',
    agents: '# agents\nagents text',
    tools: '# tools\ntools text',
    memory: '# memory\nmemory text',
    skills: '# skills\nskills text',
    skill: '# skill\nskill text',
  })

  assert.match(prompt, /name: socc/)
  assert.match(prompt, /# Canonical Identity/)
  assert.match(prompt, /identity text/)
  assert.match(prompt, /# Top-Level Skill Contract/)
  assert.match(prompt, /skill text/)
})

async function seedUpstreamAgents(root) {
  const upstreamRoot = join(root, 'upstream', '.agents')
  const socCopilotRoot = join(upstreamRoot, 'soc-copilot')
  const referencesRoot = join(socCopilotRoot, 'references')
  const rulesRoot = join(upstreamRoot, 'rules')
  const workflowsRoot = join(upstreamRoot, 'workflows')

  await Promise.all([
    mkdir(referencesRoot, { recursive: true }),
    mkdir(join(socCopilotRoot, 'skills'), { recursive: true }),
    mkdir(rulesRoot, { recursive: true }),
    mkdir(workflowsRoot, { recursive: true }),
  ])

  const files = {
    [join(socCopilotRoot, 'identity.md')]: '# identity\nidentity text\n',
    [join(socCopilotRoot, 'SOUL.md')]: '# soul\nsoul text\n',
    [join(socCopilotRoot, 'USER.md')]: '# user\nuser text\n',
    [join(socCopilotRoot, 'AGENTS.md')]: '# agents\nagents text\n',
    [join(socCopilotRoot, 'TOOLS.md')]: '# tools\ntools text\n',
    [join(socCopilotRoot, 'MEMORY.md')]: '# memory\nmemory text\n',
    [
      join(socCopilotRoot, 'skills.md')
    ]: '# skills\n- `soc-generalist`\n- `payload-triage`\n- `phishing-analysis`\n- `malware-behavior`\n- `suspicious-url`\n',
    [join(socCopilotRoot, 'SKILL.md')]: '# skill\nskill text\n',
    [join(referencesRoot, 'evidence-rules.md')]: '# evidence\nfacts first\n',
    [join(referencesRoot, 'output-contract.md')]: '# output\ncontract\n',
    [join(referencesRoot, 'ioc-extraction.md')]: '# ioc\nextract\n',
    [join(referencesRoot, 'mitre-guidance.md')]: '# mitre\nguidance\n',
    [join(rulesRoot, 'AGENT.md')]: '# agent rules\nfollow behavior rules\n',
    [join(rulesRoot, 'TOOLS.md')]: '# tools rules\nfollow tooling rules\n',
    [join(rulesRoot, 'MEMORY.md')]: '# memory rules\nstable conventions\n',
    [join(workflowsRoot, 'SOP.md')]: '# sop\nhandle iocs declaratively\n',
  }

  await Promise.all(
    Object.entries(files).map(([filePath, content]) =>
      writeFile(filePath, content, 'utf8'),
    ),
  )

  for (const skillName of ALL_TEST_SKILLS) {
    const skillDir = join(socCopilotRoot, 'skills', skillName)
    await mkdir(skillDir, { recursive: true })
    await writeFile(
      join(skillDir, 'SKILL.md'),
      `---\ndescription: ${skillName}\n---\n# ${skillName}\nUse ${skillName}\n`,
      'utf8',
    )
  }

  return upstreamRoot
}

test('syncSoccCanonicalFromUpstream mirrors rules, workflow, and soc-copilot', async () => {
  const root = await mkdtemp(join(tmpdir(), 'socc-soul-sync-'))
  await writeFile(join(root, 'package.json'), '{"name":"socc-test"}', 'utf8')
  const upstreamRoot = await seedUpstreamAgents(root)

  const result = await syncSoccCanonicalFromUpstream(root, upstreamRoot)
  const canonicalAgent = await readFile(
    join(root, 'socc-canonical', '.agents', 'soc-copilot', 'AGENTS.md'),
    'utf8',
  )
  const canonicalRule = await readFile(
    join(root, 'socc-canonical', '.agents', 'rules', 'AGENT.md'),
    'utf8',
  )
  const canonicalWorkflow = await readFile(
    join(root, 'socc-canonical', '.agents', 'workflows', 'SOP.md'),
    'utf8',
  )

  assert.equal(result.upstreamRoot, upstreamRoot)
  assert.match(canonicalAgent, /agents text/)
  assert.match(canonicalRule, /behavior rules/)
  assert.match(canonicalWorkflow, /handle iocs declaratively/)
})

test('syncSoccSoul generates canonical, runtime rules, all runtime skills, and manifest', async () => {
  const root = await mkdtemp(join(tmpdir(), 'socc-soul-runtime-'))
  await writeFile(join(root, 'package.json'), '{"name":"socc-test"}', 'utf8')
  const upstreamRoot = await seedUpstreamAgents(root)

  const first = await syncSoccSoul(root, { upstreamRoot })
  const second = await syncSoccSoul(root, { upstreamRoot })

  const generated = await readFile(first.generatedAgentPath, 'utf8')
  const runtime = await readFile(first.runtimeAgentPath, 'utf8')
  const runtimeRules = await readFile(first.runtimeRulesPath, 'utf8')
  const manifest = JSON.parse(
    await readFile(first.generatedManifestPath, 'utf8'),
  )
  const runtimeSkillEntries = await Promise.all(
    ALL_TEST_SKILLS.map(skill =>
      readFile(join(first.runtimeSkillsDir, skill, 'SKILL.md'), 'utf8'),
    ),
  )
  const runtimeReference = await readFile(
    join(root, '.socc', 'references', 'evidence-rules.md'),
    'utf8',
  )

  assert.equal(generated, runtime)
  assert.match(generated, /identity text/)
  assert.doesNotMatch(generated, /behavior rules/)
  assert.match(runtimeRules, /Global Behavior Rules/)
  assert.match(runtimeRules, /behavior rules/)
  assert.match(runtimeRules, /IOC Handling SOP/)
  assert.match(runtimeRules, /handle iocs declaratively/)
  assert.match(runtimeReference, /facts first/)
  assert.deepEqual(
    manifest.runtimeSkillNames,
    ALL_TEST_SKILLS,
  )
  assert.ok(manifest.sourceBlocks.rulesAgent.sha256)
  assert.ok(manifest.sourceBlocks.workflowSop.mtimeMs)
  assert.ok(
    manifest.runtimeSkills.every(skill => ALL_TEST_SKILLS.includes(skill.name)),
  )
  assert.equal(first.runtimeRulesPath, second.runtimeRulesPath)
  assert.deepEqual(first.runtimeSkillNames, second.runtimeSkillNames)
  for (const content of runtimeSkillEntries) {
    assert.match(content, /Use/)
  }
})

test('direct bootstrap skips canonical sync when only packaged .socc runtime exists', async () => {
  const root = await mkdtemp(join(tmpdir(), 'socc-soul-packaged-'))
  const packagedScriptPath = join(root, 'scripts', 'bootstrap-socc-soul.mjs')
  await writeFile(join(root, 'package.json'), '{"name":"socc-test"}', 'utf8')
  await mkdir(join(root, 'scripts'), { recursive: true })
  await writeFile(
    packagedScriptPath,
    await readFile(bootstrapScriptPath, 'utf8'),
    'utf8',
  )
  await mkdir(join(root, '.socc', 'agents'), { recursive: true })
  await writeFile(
    join(root, '.socc', 'agents', 'socc.md'),
    '---\nname: socc\ndescription: packaged runtime\n---\n# prompt\n',
    'utf8',
  )

  const { stdout } = await execFileAsync(
    process.execPath,
    [packagedScriptPath],
    { cwd: root },
  )

  assert.match(stdout, /skipping canonical sync/i)
})
