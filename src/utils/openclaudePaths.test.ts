import { afterEach, describe, expect, mock, test } from 'bun:test'
import * as fsPromises from 'fs/promises'
import { homedir } from 'os'
import { join } from 'path'

const originalEnv = { ...process.env }
const originalArgv = [...process.argv]

async function importFreshEnvUtils() {
  return import(`./envUtils.ts?ts=${Date.now()}-${Math.random()}`)
}

async function importFreshSettings() {
  return import(`./settings/settings.ts?ts=${Date.now()}-${Math.random()}`)
}

async function importFreshLocalInstaller() {
  return import(`./localInstaller.ts?ts=${Date.now()}-${Math.random()}`)
}

afterEach(() => {
  process.env = { ...originalEnv }
  process.argv = [...originalArgv]
  mock.restore()
})

describe('SOCC paths', () => {
  test('defaults user config home to ~/.socc', async () => {
    delete process.env.SOCC_CONFIG_DIR
    const { resolveSoccConfigHomeDir } = await importFreshEnvUtils()

    expect(
      resolveSoccConfigHomeDir({
        homeDir: homedir(),
        soccExists: true,
      }),
    ).toBe(join(homedir(), '.socc'))
  })

  test('uses ~/.socc even when no prior config exists', async () => {
    delete process.env.SOCC_CONFIG_DIR
    const { resolveSoccConfigHomeDir } = await importFreshEnvUtils()

    expect(
      resolveSoccConfigHomeDir({
        homeDir: homedir(),
        soccExists: false,
      }),
    ).toBe(join(homedir(), '.socc'))
  })

  test('uses SOCC_CONFIG_DIR override when provided', async () => {
    process.env.SOCC_CONFIG_DIR = '/tmp/custom-socc'
    const { getSoccConfigHomeDir, resolveSoccConfigHomeDir } =
      await importFreshEnvUtils()

    expect(getSoccConfigHomeDir()).toBe('/tmp/custom-socc')
    expect(
      resolveSoccConfigHomeDir({
        configDirEnv: '/tmp/custom-socc',
      }),
    ).toBe('/tmp/custom-socc')
  })

  test('project and local settings paths use .socc', async () => {
    const { getRelativeSettingsFilePathForSource } = await importFreshSettings()

    expect(getRelativeSettingsFilePathForSource('projectSettings')).toBe(
      '.socc/settings.json',
    )
    expect(getRelativeSettingsFilePathForSource('localSettings')).toBe(
      '.socc/settings.local.json',
    )
  })

  test('local installer uses socc wrapper path', async () => {
    delete process.env.SOCC_CONFIG_DIR
    const { getLocalClaudePath } = await importFreshLocalInstaller()

    expect(getLocalClaudePath()).toBe(
      join(homedir(), '.socc', 'local', 'socc'),
    )
  })

  test('local installation detection matches .socc path', async () => {
    const { isManagedLocalInstallationPath } =
      await importFreshLocalInstaller()

    expect(
      isManagedLocalInstallationPath(
        `${join(homedir(), '.socc', 'local')}/node_modules/.bin/socc`,
      ),
    ).toBe(true)
  })

  test('candidate local install dir only includes socc path', async () => {
    const { getCandidateLocalInstallDirs } = await importFreshLocalInstaller()

    expect(
      getCandidateLocalInstallDirs({
        configHomeDir: join(homedir(), '.socc'),
        homeDir: homedir(),
      }),
    ).toEqual([join(homedir(), '.socc', 'local')])
  })

  test('local installs are detected only from socc binary path', async () => {
    mock.module('fs/promises', () => ({
      ...fsPromises,
      access: async (path: string) => {
        if (
          path === join(homedir(), '.socc', 'local', 'node_modules', '.bin', 'socc')
        ) {
          return
        }
        throw Object.assign(new Error('ENOENT'), { code: 'ENOENT' })
      },
    }))

    const { getDetectedLocalInstallDir, localInstallationExists } =
      await importFreshLocalInstaller()

    expect(await localInstallationExists()).toBe(true)
    expect(await getDetectedLocalInstallDir()).toBe(
      join(homedir(), '.socc', 'local'),
    )
  })
})
