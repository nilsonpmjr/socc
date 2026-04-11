import type { AgentDefinition } from '../tools/AgentTool/loadAgentsDir.js'

const SOCC_DEFAULT_AGENT_TYPE = 'socc'

export function resolveMainThreadAgentDefinition(
  activeAgents: AgentDefinition[],
  requestedAgentType?: string,
): AgentDefinition | undefined {
  if (requestedAgentType) {
    return activeAgents.find(agent => agent.agentType === requestedAgentType)
  }

  return activeAgents.find(
    agent => agent.agentType.toLowerCase() === SOCC_DEFAULT_AGENT_TYPE,
  )
}
