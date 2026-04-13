import { mkdir } from 'node:fs/promises'
import { homedir } from 'node:os'
import { join, resolve } from 'node:path'
import { env } from './env.js'

export type WindowsWorkspaceLayout = {
  configHome: string
  documentsDir: string
  generatedAlertsDir: string
  modelsDir: string
  generatedNotesDir: string
  trainingDir: string
}

export function getWindowsWorkspaceLayout(
  envLike: NodeJS.ProcessEnv = process.env,
): WindowsWorkspaceLayout | null {
  if (env.platform !== 'win32') {
    return null
  }

  const userProfile = envLike.USERPROFILE || envLike.HOME || homedir()
  const configHome =
    envLike.SOCC_CONFIG_DIR && envLike.SOCC_CONFIG_DIR.trim().length > 0
      ? resolve(envLike.SOCC_CONFIG_DIR)
      : join(userProfile, '.socc')
  const documentsDir = join(userProfile, 'Documents')

  return {
    configHome,
    documentsDir,
    generatedAlertsDir: join(documentsDir, 'Alertas_Gerados'),
    modelsDir: join(documentsDir, 'Modelos'),
    generatedNotesDir: join(documentsDir, 'Notas_Geradas'),
    trainingDir: join(documentsDir, 'Training'),
  }
}

export async function ensureWindowsWorkspaceLayout(
  envLike: NodeJS.ProcessEnv = process.env,
): Promise<WindowsWorkspaceLayout | null> {
  const layout = getWindowsWorkspaceLayout(envLike)
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
