import { describe, expect, test } from 'bun:test'

import type { AgentDefinition } from '../tools/AgentTool/loadAgentsDir.js'
import { resolveMainThreadAgentDefinition } from './defaultMainAgent.js'

function makeAgent(agentType: string, source: AgentDefinition['source']) {
  return {
    agentType,
    whenToUse: `${agentType} agent`,
    source,
    getSystemPrompt: () => `${agentType} prompt`,
  } as AgentDefinition
}

describe('resolveMainThreadAgentDefinition', () => {
  test('uses the requested agent when explicitly provided', () => {
    const requested = makeAgent('forensics', 'userSettings')
    const fallback = makeAgent('socc', 'userSettings')

    expect(
      resolveMainThreadAgentDefinition([fallback, requested], 'forensics'),
    ).toBe(requested)
  })

  test('falls back to socc when no agent is explicitly requested', () => {
    const fallback = makeAgent('socc', 'userSettings')
    const other = makeAgent('reviewer', 'userSettings')

    expect(resolveMainThreadAgentDefinition([other, fallback])).toBe(fallback)
  })

  test('matches the socc fallback case-insensitively', () => {
    const fallback = makeAgent('SOCC', 'userSettings')

    expect(resolveMainThreadAgentDefinition([fallback])).toBe(fallback)
  })

  test('returns undefined when the requested agent does not exist', () => {
    const fallback = makeAgent('socc', 'userSettings')

    expect(
      resolveMainThreadAgentDefinition([fallback], 'missing-agent'),
    ).toBeUndefined()
  })
})
