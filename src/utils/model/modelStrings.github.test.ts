import { afterEach, expect, test } from 'bun:test'

import { resetModelStringsForTestingOnly } from '../../bootstrap/state.js'
import { parseUserSpecifiedModel } from './model.js'
import { getModelStrings } from './modelStrings.js'

const originalEnv = {
  SOCC_USE_GITHUB: process.env.SOCC_USE_GITHUB,
  SOCC_USE_OPENAI: process.env.SOCC_USE_OPENAI,
  SOCC_USE_GEMINI: process.env.SOCC_USE_GEMINI,
  SOCC_USE_BEDROCK: process.env.SOCC_USE_BEDROCK,
  SOCC_USE_VERTEX: process.env.SOCC_USE_VERTEX,
  SOCC_USE_FOUNDRY: process.env.SOCC_USE_FOUNDRY,
}

function clearProviderFlags(): void {
  delete process.env.SOCC_USE_GITHUB
  delete process.env.SOCC_USE_OPENAI
  delete process.env.SOCC_USE_GEMINI
  delete process.env.SOCC_USE_BEDROCK
  delete process.env.SOCC_USE_VERTEX
  delete process.env.SOCC_USE_FOUNDRY
}

afterEach(() => {
  process.env.SOCC_USE_GITHUB = originalEnv.SOCC_USE_GITHUB
  process.env.SOCC_USE_OPENAI = originalEnv.SOCC_USE_OPENAI
  process.env.SOCC_USE_GEMINI = originalEnv.SOCC_USE_GEMINI
  process.env.SOCC_USE_BEDROCK = originalEnv.SOCC_USE_BEDROCK
  process.env.SOCC_USE_VERTEX = originalEnv.SOCC_USE_VERTEX
  process.env.SOCC_USE_FOUNDRY = originalEnv.SOCC_USE_FOUNDRY
  resetModelStringsForTestingOnly()
})

test('GitHub provider model strings are concrete IDs', () => {
  clearProviderFlags()
  process.env.SOCC_USE_GITHUB = '1'

  const modelStrings = getModelStrings()

  for (const value of Object.values(modelStrings)) {
    expect(typeof value).toBe('string')
    expect(value.trim().length).toBeGreaterThan(0)
  }
})

test('GitHub provider model strings are safe to parse', () => {
  clearProviderFlags()
  process.env.SOCC_USE_GITHUB = '1'

  const modelStrings = getModelStrings()

  expect(() => parseUserSpecifiedModel(modelStrings.sonnet46 as any)).not.toThrow()
})
