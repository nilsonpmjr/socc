import { afterEach, expect, test } from 'bun:test'
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { resetStateForTests, setAdditionalDirectoriesForClaudeMd, setCwdState, setOriginalCwd, setProjectRoot } from '../bootstrap/state.js'
import { syncSoccSoul } from '../../scripts/bootstrap-socc-soul.mjs'
import { getSkillDirCommands, clearSkillCaches } from '../skills/loadSkillsDir.ts'
import { clearMemoryFileCaches, getMemoryFiles } from './claudemd.js'

const ALL_TEST_SKILLS = [
  'malware-behavior',
  'payload-triage',
  'phishing-analysis',
  'soc-generalist',
  'suspicious-url',
  'humanizer',
].sort()

function seedUpstreamAgents(root: string): string {
  const upstreamRoot = join(root, 'upstream', '.agents')
  const socCopilotRoot = join(upstreamRoot, 'soc-copilot')
  const referencesRoot = join(socCopilotRoot, 'references')
  const rulesRoot = join(upstreamRoot, 'rules')
  const workflowsRoot = join(upstreamRoot, 'workflows')

  mkdirSync(referencesRoot, { recursive: true })
  mkdirSync(join(socCopilotRoot, 'skills'), { recursive: true })
  mkdirSync(rulesRoot, { recursive: true })
  mkdirSync(workflowsRoot, { recursive: true })

  const files: Record<string, string> = {
    [join(socCopilotRoot, 'identity.md')]: '# identity\nidentity text\n',
    [join(socCopilotRoot, 'SOUL.md')]: '# soul\nsoul text\n',
    [join(socCopilotRoot, 'USER.md')]: '# user\nuser text\n',
    [join(socCopilotRoot, 'AGENTS.md')]: '# agents\nagents text\n',
    [join(socCopilotRoot, 'TOOLS.md')]: '# tools\ntools text\n',
    [join(socCopilotRoot, 'MEMORY.md')]: '# memory\nmemory text\n',
    [join(socCopilotRoot, 'skills.md')]:
      '# skills\n- `soc-generalist`\n- `payload-triage`\n- `phishing-analysis`\n- `malware-behavior`\n- `suspicious-url`\n',
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

  for (const [filePath, content] of Object.entries(files)) {
    writeFileSync(filePath, content, 'utf8')
  }

  for (const skillName of ALL_TEST_SKILLS) {
    const skillDir = join(socCopilotRoot, 'skills', skillName)
    mkdirSync(skillDir, { recursive: true })
    writeFileSync(
      join(skillDir, 'SKILL.md'),
      `---\ndescription: ${skillName}\n---\n# ${skillName}\nUse ${skillName}\n`,
      'utf8',
    )
  }

  return upstreamRoot
}

let tempRoot: string | null = null
let previousConfigDir: string | undefined

afterEach(() => {
  clearSkillCaches()
  clearMemoryFileCaches()
  resetStateForTests()
  if (previousConfigDir === undefined) {
    delete process.env.CLAUDE_CONFIG_DIR
  } else {
    process.env.CLAUDE_CONFIG_DIR = previousConfigDir
  }
  if (tempRoot) {
    rmSync(tempRoot, { recursive: true, force: true })
    tempRoot = null
  }
})

test('generated runtime rules and all upstream skills are visible to native loaders', async () => {
  tempRoot = mkdtempSync(join(tmpdir(), 'socc-runtime-loaders-'))
  previousConfigDir = process.env.CLAUDE_CONFIG_DIR
  process.env.CLAUDE_CONFIG_DIR = join(tempRoot, 'isolated-config')

  writeFileSync(join(tempRoot, 'package.json'), '{"name":"socc-test"}', 'utf8')
  mkdirSync(process.env.CLAUDE_CONFIG_DIR, { recursive: true })

  const upstreamRoot = seedUpstreamAgents(tempRoot)
  await syncSoccSoul(tempRoot, { upstreamRoot })

  const workspace = join(tempRoot, 'workspace')
  mkdirSync(workspace, { recursive: true })

  resetStateForTests()
  setOriginalCwd(workspace)
  setProjectRoot(workspace)
  setCwdState(workspace)
  setAdditionalDirectoriesForClaudeMd([])
  clearSkillCaches()
  clearMemoryFileCaches()

  const memoryFiles = await getMemoryFiles()
  const rulesFile = memoryFiles.find(file =>
    file.path.endsWith('.claude/rules/socc-business-rules.md'),
  )
  const skills = await getSkillDirCommands(workspace)
  const promptSkills = skills
    .filter(skill => skill.type === 'prompt')
    .map(skill => skill.name)
    .sort()

  expect(rulesFile).toBeDefined()
  expect(rulesFile?.content).toContain('follow behavior rules')
  expect(rulesFile?.content).toContain('handle iocs declaratively')
  expect(promptSkills).toEqual(ALL_TEST_SKILLS)
})
