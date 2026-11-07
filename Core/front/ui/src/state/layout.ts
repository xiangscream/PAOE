import type { AgentSummary, BoardLayout, LayoutNode } from '../types'

export const DEFAULT_VIEWPORT = { x: 0, y: 0, zoom: 1 }

export function defaultNodes(agents: AgentSummary[]): Record<string, LayoutNode> {
  const columns = Math.min(4, Math.max(1, Math.ceil(Math.sqrt(agents.length || 1))))
  const nodes: Record<string, LayoutNode> = {}
  agents.forEach((agent, index) => {
    const column = index % columns
    const row = Math.floor(index / columns)
    nodes[agent.id] = { x: 60 + column * 308, y: 50 + row * 184 }
  })
  return nodes
}

export function mergeLayout(agents: AgentSummary[], saved?: Partial<BoardLayout> | null): BoardLayout {
  const base = defaultNodes(agents)
  const nodes: Record<string, LayoutNode> = {}
  for (const agent of agents) {
    const candidate = saved?.nodes?.[agent.id]
    nodes[agent.id] = candidate ? { ...candidate } : base[agent.id]
  }
  const viewport = saved?.viewport
  return {
    nodes,
    viewport: { ...(viewport || DEFAULT_VIEWPORT) },
  }
}
