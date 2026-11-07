<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, shallowRef, watch } from 'vue'
import { VueFlow, useVueFlow, type Connection, type Edge, type Node, type NodeMouseEvent } from '@vue-flow/core'
import PersonNode from './PersonNode.vue'
import type { AgentSummary, BoardLayout } from '../types'
import { defaultNodes } from '../state/layout'
import { canStartCollaboration } from '../state/team'

const props = defineProps<{
  agents: AgentSummary[]
  layout: BoardLayout
  project: string
  fitOnLoad: boolean
  selectedIds: string[]
}>()
const emit = defineEmits<{
  (e: 'node-click', id: string): void
  (e: 'node-context', payload: { id: string }): void
  (e: 'connect', payload: { source: string; target: string }): void
  (e: 'save', payload: BoardLayout): void
  (e: 'selection-change', ids: string[]): void
}>()
const nodes = shallowRef<Node[]>([])
const edges = shallowRef<Edge[]>([])
const { fitView, getNodes, getSelectedNodes, getViewport, setViewport, setCenter } = useVueFlow()
let initializing = true

async function initialize() {
  if (props.fitOnLoad) await fitView({ padding: 0.05, maxZoom: 1 })
  else await setViewport(props.layout.viewport)
  initializing = false
  emit('selection-change',getSelectedNodes.value.map(node=>node.id))
}
function save() {
  if (initializing) return
  const positions: BoardLayout['nodes'] = {}
  for (const node of getNodes.value) positions[node.id] = { ...node.position }
  emit('save', { nodes: positions, viewport: { ...getViewport() } })
}
function onNodeClick({event, node}: NodeMouseEvent) {
  if (event.ctrlKey || event.metaKey || event.shiftKey) return
  emit('node-click', node.id)
}
function onContextMenu({event, node}: NodeMouseEvent) {
  event.preventDefault()
  emit('node-context', { id: node.id })
}
watch(()=>getSelectedNodes.value.map(node=>node.id),ids=>{if(!initializing)emit('selection-change',ids)})
function onConnect({source, target}: Connection) {
  if (source === target) return
  edges.value = [{id:'proposed-collaboration',source,target,style:{stroke:'var(--accent)',strokeDasharray:'6 4'}}]
  emit('connect', {source,target})
}
async function resetLayout() {
  const positions = defaultNodes(props.agents)
  nodes.value = nodes.value.map(node => ({...node, position: positions[node.id]}))
  edges.value = []
  await nextTick()
  await fitView({padding:0.05,maxZoom:1})
  save()
}
function select(ids: string[]) {
  const selected = new Set(ids)
  nodes.value = nodes.value.map(node => ({...node, selected:selected.has(node.id)}))
}
async function locate(id: string) {
  const node = getNodes.value.find(item => item.id === id)
  if (node) await setCenter(node.position.x + node.dimensions.width / 2, node.position.y + node.dimensions.height / 2, {zoom:1})
}
defineExpose({resetLayout,locate,select,clearEdges:()=>{edges.value=[]},fit:()=>fitView({padding:0.05,maxZoom:1})})
onBeforeUnmount(()=>{initializing=true})
onMounted(() => {
  nodes.value = props.agents.map(agent => ({
    id:agent.id,type:'person',position:{...props.layout.nodes[agent.id]},
    data:{agent,openLibrary:(id:string)=>emit('node-context',{id})},
    connectable:canStartCollaboration(agent),selected:props.selectedIds.includes(agent.id),
  }))
})
</script>

<template>
  <VueFlow v-model:nodes="nodes" v-model:edges="edges" :min-zoom="0.25" :max-zoom="2.5"
    :nodes-draggable="true" :elements-selectable="true" :pan-on-drag="true"
    :multi-selection-key-code="['Control','Meta']" :selection-key-code="'Shift'"
    :zoom-on-double-click="false" :node-drag-threshold="4"
    @nodes-initialized="initialize" @node-click="onNodeClick" @node-context-menu="onContextMenu"
    @connect="onConnect" @node-drag-stop="save" @viewport-change-end="save">
    <template #node-person="nodeProps"><PersonNode v-bind="nodeProps" /></template>
  </VueFlow>
</template>
