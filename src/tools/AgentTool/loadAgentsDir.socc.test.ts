import { expect, test } from 'bun:test'
import { mkdtempSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

import { buildEffectiveSystemPrompt } from '../../utils/systemPrompt.js'
import {
  clearAgentDefinitionsCache,
  getAgentDefinitionsWithOverrides,
} from './loadAgentsDir.js'

test('loads the canonical socc agent outside the repo when SOCC_PACKAGE_ROOT is set', async () => {
  const previousRoot = process.env.SOCC_PACKAGE_ROOT
  const tempCwd = mkdtempSync(join(tmpdir(), 'socc-canonical-agent-'))

  try {
    process.env.SOCC_PACKAGE_ROOT =
      '/home/nilsonpmjr/.gemini/antigravity/scratch/socc'
    clearAgentDefinitionsCache()

    const defs = await getAgentDefinitionsWithOverrides(tempCwd)
    const soccAgent = defs.activeAgents.find(
      agent => agent.agentType.toLowerCase() === 'socc',
    )

    expect(soccAgent).toBeDefined()
    expect(soccAgent?.source).toBe('policySettings')
  } finally {
    if (previousRoot === undefined) {
      delete process.env.SOCC_PACKAGE_ROOT
    } else {
      process.env.SOCC_PACKAGE_ROOT = previousRoot
    }
    clearAgentDefinitionsCache()
  }
})

test('canonical socc agent resolves to the same base prompt in interactive and headless flows', async () => {
  const previousRoot = process.env.SOCC_PACKAGE_ROOT
  const tempCwd = mkdtempSync(join(tmpdir(), 'socc-canonical-prompt-'))

  try {
    process.env.SOCC_PACKAGE_ROOT =
      '/home/nilsonpmjr/.gemini/antigravity/scratch/socc'
    clearAgentDefinitionsCache()

    const defs = await getAgentDefinitionsWithOverrides(tempCwd)
    const soccAgent = defs.activeAgents.find(
      agent => agent.agentType.toLowerCase() === 'socc',
    )

    expect(soccAgent).toBeDefined()

    const headlessPrompt = soccAgent?.getSystemPrompt()
    const interactivePrompt = buildEffectiveSystemPrompt({
      mainThreadAgentDefinition: soccAgent,
      toolUseContext: {
        options: {
          agentDefinitions: defs,
        },
      } as never,
      customSystemPrompt: undefined,
      defaultSystemPrompt: ['default prompt placeholder'],
      appendSystemPrompt: undefined,
    })

    expect(headlessPrompt).toBeTruthy()
    expect(Array.from(interactivePrompt)).toEqual([headlessPrompt as string])
  } finally {
    if (previousRoot === undefined) {
      delete process.env.SOCC_PACKAGE_ROOT
    } else {
      process.env.SOCC_PACKAGE_ROOT = previousRoot
    }
    clearAgentDefinitionsCache()
  }
})
