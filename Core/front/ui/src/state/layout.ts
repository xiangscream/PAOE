import type { AgentSummary, BoardLayout, LayoutNode } from '../types'

export const DEFAULT_VIEWPORT = { x: 0, y: 0, zoom: 0.9 }

export function defaultNodes(agents: AgentSummary[]): Record<string, LayoutNode> {
  const columns = Math.min(4, Math.max(1, Math.ceil(Math.sqrt(agents.length || 1))))
  const nodes: Record<string, LayoutNode> = {}
  agents.forEach((agent, index) => {
    const column = index % columns
    const row = Math.floor(index / columns)
    nodes[agent.id] = { x: 80 + column * 260, y: 90 + row * 156 }
  })
  return nodes
}

function finite(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

export function mergeLayout(agents: AgentSummary[], saved?: Partial<BoardLayout> | null): BoardLayout {
  const base = defaultNodes(agents)
  const nodes: Record<string, LayoutNode> = {}
  for (const agent of agents) {
    const candidate = saved?.nodes?.[agent.id]
    nodes[agent.id] = candidate
      ? { x: finite(candidate.x, base[agent.id].x), y: finite(candidate.y, base[agent.id].y) }
      : base[agent.id]
  }
  const viewport = saved?.viewport
  return {
    nodes,
    viewport: viewport
      ? {
          x: finite(viewport.x, DEFAULT_VIEWPORT.x),
          y: finite(viewport.y, DEFAULT_VIEWPORT.y),
          zoom: Math.min(2.5, Math.max(0.2, finite(viewport.zoom, DEFAULT_VIEWPORT.zoom))),
        }
      : { ...DEFAULT_VIEWPORT },
  }
}

export function clampNode(position: LayoutNode, width: number, height: number): LayoutNode {
  const maxX = Math.max(0, width - 240)
  const maxY = Math.max(0, height - 140)
  return {
    x: Math.min(maxX, Math.max(0, position.x)),
    y: Math.min(maxY, Math.max(0, position.y)),
  }
}
