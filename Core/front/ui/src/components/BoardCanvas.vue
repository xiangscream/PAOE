<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { VueFlow, useVueFlow, type Connection, type Edge, type Node } from '@vue-flow/core'
import PersonNode from './PersonNode.vue'
import type { AgentSummary, BoardLayout } from '../types'
import { clampNode } from '../state/layout'

const props = defineProps<{
  agents: AgentSummary[]
  layout: BoardLayout
  project: string
}>()

const emit = defineEmits<{
  (e: 'node-click', id: string): void
  (e: 'node-context', payload: { id: string; event?: MouseEvent }): void
  (e: 'connect', payload: { source: string; target: string }): void
  (e: 'save', payload: BoardLayout): void
  (e: 'selection-change', ids: string[]): void
}>()

const nodes = ref<Node[]>([])
const edges = ref<Edge[]>([])
const { fitView, getViewport, setViewport, screenToFlowCoordinate } = useVueFlow()

function buildNodes() {
  nodes.value = props.agents.map(agent => ({
    id: agent.id,
    type: 'person',
    position: { ...(props.layout.nodes[agent.id] || { x: 80, y: 90 }) },
    data: { agent, openLibrary: (id: string) => emit('node-context', { id }) },
    selected: false,
  }))
}

function applyViewport() {
  const viewport = props.layout.viewport
  if (viewport && Number.isFinite(viewport.zoom) && viewport.zoom > 0) {
    void nextTick(() => setViewport({ x: viewport.x, y: viewport.y, zoom: viewport.zoom }))
  } else {
    void nextTick(() => fitView({ padding: 0.14 }))
  }
}

function snapshot(): BoardLayout {
  const positions: BoardLayout['nodes'] = {}
  for (const node of nodes.value) positions[node.id] = { x: node.position.x, y: node.position.y }
  const viewport = getViewport()
  return {
    nodes: positions,
    viewport: { x: viewport.x, y: viewport.y, zoom: viewport.zoom },
  }
}

function save() {
  emit('save', snapshot())
}

function onNodeClick(event: { node: Node }) {
  emit('node-click', event.node.id)
}

function onContextMenu(event: { event: MouseEvent; node: Node }) {
  event.event.preventDefault()
  emit('node-context', { id: event.node.id, event: event.event })
}

function onConnect(connection: Connection) {
  if (!connection.source || !connection.target || connection.source === connection.target) return
  edges.value = [
    ...edges.value,
    {
      id: `draft-${connection.source}-${connection.target}-${Date.now()}`,
      source: connection.source,
      target: connection.target,
      animated: false,
      style: { stroke: 'var(--accent)', strokeDasharray: '6 4' },
    },
  ]
  emit('connect', { source: connection.source, target: connection.target })
}

function selectionChanged(event: { nodes: Node[] }) {
  emit('selection-change', event.nodes.map(node => node.id))
}

function resetLayout() {
  edges.value = []
  emit('save', { nodes: {}, viewport: { x: 0, y: 0, zoom: 0.9 } })
}

function clearEdges() {
  edges.value = []
}

function locate(id: string) {
  const node = nodes.value.find(item => item.id === id)
  if (!node) return
  void setViewport({ x: -node.position.x + 320, y: -node.position.y + 240, zoom: 1 })
}

defineExpose({ resetLayout, clearEdges, locate, fit: () => fitView({ padding: 0.14 }) })

watch(() => props.agents, () => {
  buildNodes()
  applyViewport()
}, { deep: true })

watch(() => props.layout, (value) => {
  for (const node of nodes.value) {
    const saved = value?.nodes?.[node.id]
    if (saved) node.position = { ...saved }
  }
}, { deep: true })

onMounted(() => {
  buildNodes()
  applyViewport()
})
</script>

<template>
  <VueFlow
    v-model:nodes="nodes"
    v-model:edges="edges"
    :min-zoom="0.25"
    :max-zoom="1.8"
    :nodes-draggable="true"
    :nodes-connectable="true"
    :elements-selectable="true"
    :selection-on-drag="true"
    :pan-on-drag="true"
    :zoom-on-double-click="false"
    :fit-view-on-init="false"
    :node-drag-threshold="4"
    @node-click="onNodeClick"
    @node-context-menu="onContextMenu"
    @connect="onConnect"
    @node-drag-stop="save"
    @viewport-change-end="save"
    @selection-change="selectionChanged"
  >
    <template #node-person="nodeProps">
      <PersonNode v-bind="nodeProps" />
    </template>
  </VueFlow>
</template>
