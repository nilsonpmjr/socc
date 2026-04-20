import type { Command } from '../../commands.js'

function isSupportedPlatform(): boolean {
  if (process.platform === 'darwin') {
    return true
  }
  if (process.platform === 'win32' && process.arch === 'x64') {
    return true
  }
  return false
}

const desktop = {
  type: 'local-jsx',
  name: 'desktop',
  aliases: ['app'],
  description: 'Desktop handoff is unavailable in SOCC',
  availability: ['claude-ai'],
  isEnabled: () => false,
  get isHidden() {
    return true
  },
  load: () => import('./desktop.js'),
} satisfies Command

export default desktop
