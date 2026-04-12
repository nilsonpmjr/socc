import * as React from 'react'
import { Box, Text } from 'src/ink.js'

const WORDMARK_LINES = [
  '╔███████╗  ██████═╗ ╔███████╗ ╔███████╗',
  '██╔═════╝ ██╔═══██║ ██╔═════╝ ██╔═════╝',
  '║██████═╗ ██║   ██║ ██║       ██║      ',
  '╚════╗██║ ██║   ██║ ██║       ██║      ',
  '███████ ║ ║██████ ║ ║███████╗ ║███████╗',
  '╚═══════╝ ╚═══════╝ ╚═══════╝ ╚═══════╝',
]

export function WelcomeV2() {
  return (
    <Box flexDirection="column" width={58}>
      <Text color="claude" bold>
        Welcome to SOCC{' '}
        <Text dimColor>{`v${MACRO.DISPLAY_VERSION ?? MACRO.VERSION}`}</Text>
      </Text>
      <Box marginTop={1} flexDirection="column">
        {WORDMARK_LINES.map((line, index) => (
          <Text key={index} color="claude">
            {line}
          </Text>
        ))}
      </Box>
      <Box marginTop={1}>
        <Text dimColor>Security operations copiloto</Text>
      </Box>
    </Box>
  )
}
