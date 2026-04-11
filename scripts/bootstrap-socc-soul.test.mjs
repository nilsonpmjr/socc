import assert from 'node:assert/strict'
import { mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

import { composeSoccAgentPrompt, syncSoccSoul } from './bootstrap-socc-soul.mjs'

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

test('syncSoccSoul generates canonical and runtime artifacts', async () => {
  const root = await mkdtemp(join(tmpdir(), 'socc-soul-'))
  await writeFile(join(root, 'package.json'), '{"name":"socc-test"}', 'utf8')

  const canonicalRoot = join(root, 'socc-canonical', '.agents', 'soc-copilot')
  await mkdir(canonicalRoot, { recursive: true })

  const fixtures = {
    'identity.md': '# identity\nidentity text\n',
    'SOUL.md': '# soul\nsoul text\n',
    'USER.md': '# user\nuser text\n',
    'AGENTS.md': '# agents\nagents text\n',
    'TOOLS.md': '# tools\ntools text\n',
    'MEMORY.md': '# memory\nmemory text\n',
    'skills.md': '# skills\nskills text\n',
    'SKILL.md': '# skill\nskill text\n',
  }

  await Promise.all(
    Object.entries(fixtures).map(([name, content]) =>
      writeFile(join(canonicalRoot, name), content, 'utf8'),
    ),
  )

  const result = await syncSoccSoul(root)
  const generated = await readFile(result.generatedAgentPath, 'utf8')
  const runtime = await readFile(result.runtimeAgentPath, 'utf8')
  const manifest = JSON.parse(
    await readFile(result.generatedManifestPath, 'utf8'),
  )

  assert.equal(generated, runtime)
  assert.match(generated, /identity text/)
  assert.match(generated, /skill text/)
  assert.equal(manifest.sourceFiles.identity, join(canonicalRoot, 'identity.md'))
})
