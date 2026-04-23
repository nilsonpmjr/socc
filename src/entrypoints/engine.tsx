// Headless engine entrypoint — exposes query() as a public API for embedding.
//
// Consumers (e.g. the socc-plugin server) import from '@vantagesec/socc/engine'
// to drive SOCC programmatically from inside a Bun Worker, one per session.
// The CLI/REPL (cli.tsx) remains the primary entrypoint; this bundle is
// additive and shares the same build pipeline (feature flags, stubs, externals).

export { query } from '../query.js'
export type { QueryParams } from '../query.js'

export type {
  AssistantMessage,
  AttachmentMessage,
  Message,
  RequestStartEvent,
  StreamEvent,
  ToolUseSummaryMessage,
  TombstoneMessage,
  UserMessage,
} from '../types/message.js'

export type { SystemPrompt } from '../utils/systemPromptType.js'
export type { ToolUseContext } from '../Tool.js'
export type { CanUseToolFn } from '../hooks/useCanUseTool.js'
