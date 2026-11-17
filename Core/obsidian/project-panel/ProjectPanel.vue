<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { api, ApiError } from '../../front/ui/src/api'
import type { AgentSummary, BoardLayout, CollabResult, Dashboard, LibraryItem } from '../../front/ui/src/types'
import BoardCanvas from '../../front/ui/src/components/BoardCanvas.vue'
import PersonDrawer from '../../front/ui/src/components/PersonDrawer.vue'
import LibraryPanel from '../../front/ui/src/components/LibraryPanel.vue'
import CollaborationDialog from '../../front/ui/src/components/CollaborationDialog.vue'
import { DEFAULT_VIEWPORT, mergeLayout } from '../../front/ui/src/state/layout'
import type { CollaborationDraft } from '../../front/ui/src/state/collab'
import { canStartCollaboration, displayNumber } from '../../front/ui/src/state/team'

const props = defineProps<{
  project: string
  projectName?: string
  openCat: (roomId: string) => void
}>()

const dashboard = ref<Dashboard | null>(null)
const loading = ref(true)
const error = ref('')
const notice = ref('')
const saving = ref('')
const layout = ref<BoardLayout>({ nodes: {}, viewport: { ...DEFAULT_VIEWPORT } })
const hasSavedLayout = ref(false)
const selectedIds = ref<string[]>([])
const drawerId = ref('')
const libraryOpen = ref(false)
const libraryAgent = ref('')
const collabOpen = ref(false)
const collabInitial = ref<CollaborationDraft>({
  provider: '', receiver: '', topic: '', note: '', mode: 'chat', remind: true, reference: null,
})
const boardRef = ref<InstanceType<typeof BoardCanvas> | null>(null)
const collabRef = ref<InstanceType<typeof CollaborationDialog> | null>(null)
const attachingReference = ref(false)
const locate = ref('')
let loadingGeneration = 0

const agents = computed<AgentSummary[]>(() => {
  const list = dashboard.value?.agents || []
  const coordinator = dashboard.value?.coordinator
  return [...list].sort((a, b) => {
    if (a.id === coordinator) return -1
    if (b.id === coordinator) return 1
    return displayNumber(a).localeCompare(displayNumber(b))
  })
})
const drawerAgent = computed(() => agents.value.find(agent => agent.id === drawerId.value) || null)
const libraryAgentSummary = computed(() => agents.value.find(agent => agent.id === libraryAgent.value) || null)
const selectedAgents = computed(() => agents.value.filter(agent => selectedIds.value.includes(agent.id)))
const canCollaborate = computed(() => selectedAgents.value.length >= 2 && selectedAgents.value.every(canStartCollaboration))
const examples = computed(() => dashboard.value?.examples || { workflow: [], skill: [], tool: [] })

async function load() {
  const generation = ++loadingGeneration
  loading.value = true
  error.value = ''
  try {
    const data = await api.dashboard(props.project)
    if (generation !== loadingGeneration) return
    dashboard.value = data
    let saved: BoardLayout | null = null
    try {
      const response = await api.getLayout(props.project)
      if (generation !== loadingGeneration) return
      saved = response.layout
    } catch (problem) {
      if (!(problem instanceof ApiError) || problem.status !== 404) throw problem
      notice.value = '布局接口不可用：本次只显示默认布局，位置不会保存。'
    }
    layout.value = mergeLayout(agents.value, saved || { nodes: {}, viewport: { ...DEFAULT_VIEWPORT } })
    hasSavedLayout.value = Object.keys(saved?.nodes || {}).length > 0
    await nextTick()
    boardRef.value?.select(selectedIds.value.filter(id => agents.value.some(agent => agent.id === id)))
  } catch (problem) {
    if (generation !== loadingGeneration) return
    error.value = problem instanceof ApiError ? problem.message : String(problem)
  } finally {
    if (generation === loadingGeneration) loading.value = false
  }
}

async function saveLayout(next: BoardLayout) {
  layout.value = next
  saving.value = '保存中…'
  try {
    await api.saveLayout(props.project, next)
    saving.value = '已保存布局'
  } catch (problem) {
    saving.value = '布局未保存：' + (problem instanceof ApiError ? problem.message : String(problem))
  }
}

function openAgent(id: string) {
  drawerId.value = id
  libraryOpen.value = false
}

function openLibrary(id: string) {
  attachingReference.value = false
  libraryAgent.value = id
  libraryOpen.value = true
}

function chooseReference(id: string) {
  openLibrary(id)
  attachingReference.value = true
}

function openCollab(draft: Partial<CollaborationDraft> = {}) {
  collabInitial.value = {
    provider: 'human', receiver: '', topic: '', note: '', mode: 'chat', remind: true, reference: null, ...draft,
  }
  collabOpen.value = true
}

function fromConnection(payload: { source: string; target: string }) {
  openCollab({ provider: payload.source, receiver: payload.target, topic: '', mode: 'chat', remind: true })
}

function fromSelection() {
  const chosen = selectedAgents.value.filter(agent => canStartCollaboration(agent))
  if (chosen.length < 2) return
  openCollab({ provider: chosen[0].id, receiver: chosen[1].id, participants: chosen.map(agent => agent.id), mode: 'chat', remind: true })
}

function fromDrawer(id: string) {
  openCollab({ provider: '', receiver: id, mode: 'chat', remind: true })
}

function attachReference(item: LibraryItem) {
  libraryOpen.value = false
  if (attachingReference.value) {
    collabRef.value?.attachReference({ title: item.title || item.id, path: item.path || '', kind: item.kind, id: item.id })
    return
  }
  openCollab({
    provider: 'human', receiver: libraryAgent.value, topic: '参考：' + (item.title || item.id),
    note: '请按当前责任判断是否采用此参考。', mode: 'chat', remind: true,
    reference: { title: item.title || item.id, path: item.path || '', kind: item.kind, id: item.id },
  })
}

function sendReference(item: LibraryItem) {
  libraryOpen.value = false
  openCollab({
    provider: 'human', receiver: libraryAgent.value, topic: '参考：' + (item.title || item.id),
    note: '仅供当前协作参考；浏览没有写入，此邮件默认不提醒。', mode: 'mail', remind: false,
    reference: { title: item.title || item.id, path: item.path || '', kind: item.kind, id: item.id },
  })
}

async function completed(result: CollabResult) {
  boardRef.value?.clearEdges()
  if (result.mode === 'chat' && result.room_id) props.openCat(result.room_id)
  await load()
}

function openRoom(id: string) {
  collabOpen.value = false
  props.openCat(id)
}

function onSelectionChange(ids: string[]) {
  selectedIds.value = ids
}

function locatePerson() {
  const query = locate.value.trim().toLowerCase()
  if (!query) return
  const match = agents.value.find(agent =>
    `${agent.id} ${agent.number || ''} ${agent.name || ''} ${agent.role || ''}`.toLowerCase().includes(query),
  )
  if (!match) { notice.value = '没有匹配的成员。'; return }
  drawerId.value = match.id
  boardRef.value?.locate(match.id)
}

onMounted(() => { void load() })
</script>

<template>
  <div class="app-shell paos-project-panel">
    <header class="topbar">
      <div class="brand"><span class="brand-symbol">P</span><span>PAOE<small>项目面板</small></span></div>
      <strong class="project-label">{{ project }} <span class="hint">{{ projectName || '' }}</span></strong>
      <span class="spacer"></span>
      <span class="hint">{{ saving || (loading ? '加载中…' : `${agents.length} 位同事`) }}</span>
      <button class="btn ghost" type="button" @click="load">刷新</button>
    </header>

    <div v-if="error" class="banner error">
      {{ error }}
      <button class="btn ghost" type="button" @click="load">重试</button>
    </div>
    <div v-else-if="notice" class="banner">
      {{ notice }}
      <button class="btn ghost" type="button" @click="notice = ''">知道了</button>
    </div>

    <main class="page">
      <div class="board-wrap">
        <div class="board-surface">
          <div class="board-toolbar">
            <div class="board-title"><span>TEAM / {{ project }}</span><h1>团队画板<small>{{ agents.length }} 位同事</small></h1></div>
            <div class="board-tools">
              <form class="member-search" @submit.prevent="locatePerson">
                <input v-model="locate" aria-label="搜索成员或员工号" placeholder="搜索成员、职责…" />
                <button title="定位成员" aria-label="定位成员" type="submit">⌕</button>
              </form>
              <button class="btn ghost" type="button" @click="boardRef?.fit()">适应画布</button>
            </div>
          </div>
          <div class="canvas-area">
            <BoardCanvas
              v-if="!loading && agents.length"
              ref="boardRef"
              :agents="agents"
              :layout="layout"
              :project="project"
              :fit-on-load="!hasSavedLayout"
              :selected-ids="selectedIds"
              @node-click="openAgent"
              @node-context="openLibrary($event.id)"
              @connect="fromConnection"
              @save="saveLayout"
              @selection-change="onSelectionChange"
            />
            <div v-else-if="loading" class="hint" style="padding: 40px">读取项目团队…</div>
            <div v-else class="empty-board"><h2>团队还没有成员</h2><p>请检查项目 TEAM 与登记。</p><button class="btn" @click="load">刷新</button></div>
          </div>

          <div v-if="selectedIds.length" class="action-bar">
            <strong>{{ selectedIds.length }} 位已选</strong>
            <button v-if="canCollaborate" class="btn primary" type="button" @click="fromSelection">围绕主题协作</button>
            <button class="btn" type="button" @click="openAgent(selectedIds[0])">查看详情</button>
            <button class="btn ghost" type="button" @click="openLibrary(selectedIds[0])">选择参考</button>
            <button class="btn ghost" type="button" @click="selectedIds = []; boardRef?.select([])">清除选择</button>
          </div>

          <p class="board-help">拖动同事之间的连线，围绕一个主题开始协作。<span>Ctrl / ⌘ 多选 · 右键选参考</span></p>
        </div>
      </div>

      <PersonDrawer
        :agent="drawerAgent"
        :project="project"
        @close="drawerId = ''"
        @library="openLibrary"
        @collaborate="fromDrawer"
      />

      <LibraryPanel
        class="library-overlay"
        :open="libraryOpen"
        :agent-id="libraryAgent"
        :agent-name="libraryAgentSummary?.name || libraryAgent || ''"
        :examples="examples"
        @close="libraryOpen = false"
        @attach="attachReference"
        @send="sendReference"
      />

      <CollaborationDialog
        ref="collabRef"
        :open="collabOpen"
        :initial="collabInitial"
        :agents="agents"
        :project="project"
        @close="collabOpen = false; boardRef?.clearEdges()"
        @choose-reference="chooseReference"
        @completed="completed"
        @open-room="openRoom"
      />
    </main>
  </div>
</template>

<style scoped>
.project-label {font-size:14px;font-weight:600;white-space:nowrap}
.paos-project-panel {border-radius:0}
</style>
