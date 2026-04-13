import assert from 'node:assert/strict'
import test from 'node:test'

import { extractGitHubRepoSlug } from './repoSlug.ts'

test('keeps owner/repo input as-is', () => {
  assert.equal(extractGitHubRepoSlug('nilsonpmjr/socc'), 'nilsonpmjr/socc')
})

test('extracts slug from https GitHub URLs', () => {
  assert.equal(
    extractGitHubRepoSlug('https://github.com/nilsonpmjr/socc'),
    'nilsonpmjr/socc',
  )
  assert.equal(
    extractGitHubRepoSlug('https://www.github.com/nilsonpmjr/socc.git'),
    'nilsonpmjr/socc',
  )
})

test('extracts slug from ssh GitHub URLs', () => {
  assert.equal(
    extractGitHubRepoSlug('git@github.com:nilsonpmjr/socc.git'),
    'nilsonpmjr/socc',
  )
  assert.equal(
    extractGitHubRepoSlug('ssh://git@github.com/nilsonpmjr/socc'),
    'nilsonpmjr/socc',
  )
})

test('rejects malformed or non-GitHub URLs', () => {
  assert.equal(extractGitHubRepoSlug('https://gitlab.com/nilsonpmjr/socc'), null)
  assert.equal(extractGitHubRepoSlug('https://github.com/nilsonpmjr'), null)
  assert.equal(extractGitHubRepoSlug('not actually github.com/nilsonpmjr/socc'), null)
  assert.equal(
    extractGitHubRepoSlug('https://evil.example/?next=github.com/nilsonpmjr/socc'),
    null,
  )
  assert.equal(
    extractGitHubRepoSlug('https://github.com.evil.example/nilsonpmjr/socc'),
    null,
  )
  assert.equal(
    extractGitHubRepoSlug('https://example.com/github.com/nilsonpmjr/socc'),
    null,
  )
})
