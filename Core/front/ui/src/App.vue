<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { api, ApiError } from './api'
import type { AgentSummary, BoardLayout, CollabResult, Dashboard, LibraryItem } from './types'
import BoardCanvas from './components/BoardCanvas.vue'
import PersonDrawer from './components/PersonDrawer.vue'
import LibraryPanel from './components/LibraryPanel.vue'
import CollaborationDialog from './components/CollaborationDialog.vue'
import ChatView from './components/ChatView.vue'
import ProjectOverview from './components/ProjectOverview.vue'
import { DEFAULT_VIEWPORT, mergeLayout } from './state/layout'
import type { CollaborationDraft } from './state/collab'

type Tab = 'board' | 'chat' | 'project'
const THEMES = ['light', 'dark', 'corporate', 'retro'] as const
type Theme = (typeof THEMES)[number]

const projects = ref<Array<{ id: string; name?: string }>>([])
const project = ref(localStorage.getItem('poe.project') || '')
const dashboard = ref<Dashboard | null>(null)
const loading = ref(true)
const error = ref('')
const notice = ref('')
const tab = ref<Tab>('board')
const theme = ref<Theme>((localStorage.getItem('poe.theme') as Theme) || 'light')
const layout = ref<BoardLayout>({ nodes: {}, viewport: { ...DEFAULT_VIEWPORT } })
const layoutSupported = ref(true)
const saving = ref('')
const saveError = ref('')
let pendingSave: { project: string; layout: BoardLayout } | null = null
const selectedIds = ref<string[]>([])
const drawerId = ref('')
const libraryOpen = ref(false)
const libraryAgent = ref('')
const collabOpen = ref(false)
const collabInitial = ref<CollaborationDraft>({
  provider: '', receiver: '', topic: '', note: '', mode: 'chat', remind: true, reference: null,
})
const lastCompleted = ref<CollabResult | null>(null)
const boardRef = ref<InstanceType<typeof BoardCanvas> | null>(null)
const chatRef = ref<InstanceType<typeof ChatView> | null>(null)
const initialChatRoom = ref('')
const locate = ref('')
let saveTimer: ReturnType<typeof setTimeout> | null = null

const agents = computed<AgentSummary[]>(() => {
  const list = dashboard.value?.agents || []
  const coordinator = dashboard.value?.coordinator
  return [...list].sort((a, b) => {
    if (a.id === coordinator) return -1
    if (b.id === coordinator) return 1
    return String(a.number || a.id).localeCompare(String(b.number || b.id))
  })
})
const drawerAgent = computed(() => agents.value.find(agent => agent.id === drawerId.value) || null)
const libraryAgentSummary = computed(() => agents.value.find(agent => agent.id === libraryAgent.value) || null)
const selectedAgents = computed(() => agents.value.filter(agent => selectedIds.value.includes(agent.id)))
const canCollaborate = computed(() => selectedAgents.value.filter(a => a.can_contact !== false).length >= 2)
const examples = computed(() => dashboard.value?.examples || { workflow: [], skill: [], tool: [] })

function onThemeChange(event: Event) {
  applyTheme((event.target as HTMLSelectElement).value as Theme)
}

function applyTheme(value: Theme) {
  theme.value = value
  document.documentElement.dataset.theme = value
  localStorage.setItem('poe.theme', value)
}

async function loadProjects() {
  const data = await api.dashboard('')
  projects.value = data.projects || []
  return data
}

async function load(target = project.value) {
  loading.value = true
  error.value = ''
  notice.value = ''
  try {
    if (!projects.value.length) await loadProjects()
    const data = await api.dashboard(target)
    dashboard.value = data
    project.value = data.project || target
    localStorage.setItem('poe.project', project.value)
    let saved: BoardLayout | null = null
    let hasLayout = false
    try {
      const response = await api.getLayout(project.value)
      saved = response.layout || null
      hasLayout = !!saved && (
        Object.keys(saved.nodes || {}).length > 0 ||
        saved.viewport.x !== 0 || saved.viewport.y !== 0 || Math.abs(saved.viewport.zoom - 0.9) > 0.001
      )
      layoutSupported.value = true
    } catch (problem) {
      if (problem instanceof ApiError && problem.status === 404) {
        layoutSupported.value = false
        notice.value = '布局接口不可用：本次只显示默认布局，位置不会保存。'
      } else {
        throw problem
      }
    }
    const merged = mergeLayout(agents.value, saved || { nodes: {}, viewport: { ...DEFAULT_VIEWPORT } })
    layout.value = hasLayout ? merged : { nodes: merged.nodes, viewport: { x: 0, y: 0, zoom: 0 } }
    await nextTick()
    if (!hasLayout) boardRef.value?.fit()
    try {
      const cached = localStorage.getItem('poe.selection.' + project.value)
      if (cached) {
        const ids = JSON.parse(cached)
        if (Array.isArray(ids)) selectedIds.value = ids.filter(id => typeof id === 'string')
      }
    } catch {
      /* ignore */
    }
    selectedIds.value = selectedIds.value.filter(id => agents.value.some(agent => agent.id === id))
    await nextTick()
    boardRef.value?.select(selectedIds.value)
    if (drawerId.value && !agents.value.some(agent => agent.id === drawerId.value)) drawerId.value = ''
  } catch (problem) {
    error.value = problem instanceof ApiError ? problem.message : String(problem)
  } finally {
    loading.value = false
  }
}

function queueSave(next: BoardLayout) {
  layout.value = next
  if (!layoutSupported.value) {
    saving.value = '未保存（布局接口不可用）'
    return
  }
  const owner = project.value
  pendingSave = { project: owner, layout: next }
  saving.value = '保存中…'
  saveError.value = ''
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => void flushSave(), 500)
}

async function flushSave() {
  const job = pendingSave
  if (!job) return
  try {
    await api.saveLayout(job.project, job.layout)
    if (pendingSave === job) pendingSave = null
    if (project.value === job.project) saving.value = '已保存布局'
  } catch (problem) {
    const message = problem instanceof ApiError ? problem.message : String(problem)
    if (project.value === job.project) saving.value = '未保存'
    saveError.value = '布局保存失败：' + message
  }
}

function retrySave() {
  if (!pendingSave) return
  saveError.value = ''
  saving.value = '保存中…'
  void flushSave()
}

function openChatRoomFromQuery() {
  const room = new URLSearchParams(location.search).get('room')
  if (!room) return false
  initialChatRoom.value = room
  tab.value = 'chat'
  return true
}

function onNodeContext(payload: { id: string; event: MouseEvent }) {
  openLibrary(payload.id)
}

function onSelectionChange(ids: string[]) {
  selectedIds.value = ids
  try {
    localStorage.setItem('poe.selection.' + project.value, JSON.stringify(ids))
  } catch {
    /* selection is a convenience only */
  }
}

function openAgent(id: string) {
  drawerId.value = id
  libraryOpen.value = false
}

function openLibrary(id: string) {
  libraryAgent.value = id
  libraryOpen.value = true
}

function openCollab(draft: Partial<CollaborationDraft> = {}) {
  collabInitial.value = {
    provider: 'human',
    receiver: '',
    topic: '',
    note: '',
    mode: 'chat',
    remind: true,
    reference: null,
    ...draft,
  }
  collabOpen.value = true
}

function fromConnection(payload: { source: string; target: string }) {
  openCollab({ provider: payload.source, receiver: payload.target, topic: '', mode: 'chat', remind: true })
}

function fromSelection() {
  const chosen = selectedAgents.value.filter(a => a.can_contact !== false)
  if (chosen.length < 2) return
  openCollab({ provider: chosen[0].id, receiver: chosen[1].id, mode: 'chat', remind: true })
}

function fromDrawer(id: string) {
  openCollab({ provider: '', receiver: id, mode: 'chat', remind: true })
}

function attachReference(item: LibraryItem) {
  libraryOpen.value = false
  openCollab({
    provider: 'human',
    receiver: libraryAgent.value,
    topic: '参考：' + (item.title || item.id),
    note: '请按当前责任判断是否采用此参考。',
    mode: 'chat',
    remind: true,
    reference: { title: item.title || item.id, path: item.path || '', kind: item.kind, id: item.id },
  })
}

function sendReference(item: LibraryItem) {
  libraryOpen.value = false
  openCollab({
    provider: 'human',
    receiver: libraryAgent.value,
    topic: '参考：' + (item.title || item.id),
    note: '仅供当前协作参考；浏览没有写入，此邮件默认不提醒。',
    mode: 'mail',
    remind: false,
    reference: { title: item.title || item.id, path: item.path || '', kind: item.kind, id: item.id },
  })
}

async function completed(result: CollabResult) {
  lastCompleted.value = result
  if (result.mode === 'chat' && result.room_id) {
    initialChatRoom.value = result.room_id
  }
  await load(project.value)
}

async function openRoom(id: string) {
  collabOpen.value = false
  initialChatRoom.value = id
  tab.value = 'chat'
  await nextTick()
  await chatRef.value?.selectRoom(id)
}

function locatePerson() {
  const q = locate.value.trim().toLowerCase()
  if (!q) return
  const match = agents.value.find(agent =>
    `${agent.id} ${agent.number || ''} ${agent.name || ''} ${agent.role || ''}`.toLowerCase().includes(q),
  )
  if (!match) {
    notice.value = '没有匹配的成员。'
    return
  }
  drawerId.value = match.id
  boardRef.value?.locate(match.id)
}

function resetBoard() {
  if (!confirm('恢复默认布局？只影响坐标与视口，不改团队关系。')) return
  boardRef.value?.resetLayout()
}

function clearSelection() {
  selectedIds.value = []
}

watch(theme, value => applyTheme(value))

onMounted(() => {
  applyTheme(theme.value)
  openChatRoomFromQuery()
  void load()
})
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">PAOE 工作台<small>项目原件映射</small></div>
      <select v-model="project" class="btn" aria-label="选择项目" @change="load(project)">
        <option v-for="item in projects" :key="item.id" :value="item.id">{{ item.id }} {{ item.name || '' }}</option>
      </select>
      <nav class="nav-tabs" aria-label="主导航">
        <button :class="{ on: tab === 'board' }" @click="tab = 'board'">团队画板</button>
        <button :class="{ on: tab === 'chat' }" @click="tab = 'chat'">讨论</button>
        <button :class="{ on: tab === 'project' }" @click="tab = 'project'">项目概览</button>
      </nav>
      <span class="spacer"></span>
      <span class="hint">{{ saving || (loading ? '加载中…' : `${agents.length} 位同事`) }}</span>
      <select :value="theme" class="btn" aria-label="界面主题" @change="onThemeChange">
        <option value="light">简洁</option>
        <option value="dark">深色</option>
        <option value="corporate">商务</option>
        <option value="retro">复古</option>
      </select>
      <button class="btn ghost" @click="load(project)">刷新</button>
    </header>

    <div v-if="error" class="banner error">
      {{ error }}
      <button class="btn ghost" @click="load(project)">重试</button>
    </div>
    <div v-else-if="saveError" class="banner error">
      {{ saveError }}
      <button class="btn ghost" @click="retrySave">重试保存</button>
    </div>
    <div v-else-if="notice" class="banner">
      {{ notice }}
      <button class="btn ghost" @click="notice = ''">知道了</button>
    </div>

    <main class="page">
      <template v-if="tab === 'board'">
        <div class="board-wrap">
          <div class="board-surface">
            <div class="row" style="position: absolute; top: 12px; left: 12px; z-index: 6">
              <input v-model="locate" class="btn" style="width: 220px" placeholder="搜索成员或员工号" @keyup.enter="locatePerson" />
              <button class="btn" @click="locatePerson">定位</button>
              <button class="btn ghost" @click="boardRef?.fit()">适应画布</button>
              <button class="btn ghost" @click="resetBoard">恢复默认</button>
            </div>
            <BoardCanvas
              v-if="!loading"
              ref="boardRef"
              :agents="agents"
              :layout="layout"
              :project="project"
              @node-click="openAgent"
              @node-context="onNodeContext"
              @connect="fromConnection"
              @save="queueSave"
              @selection-change="onSelectionChange"
            />
            <div v-else class="hint" style="padding: 40px">读取项目团队…</div>

            <div v-if="selectedIds.length" class="action-bar">
              <strong>{{ selectedIds.length }} 位已选</strong>
              <button v-if="canCollaborate" class="btn primary" @click="fromSelection">围绕主题协作</button>
              <button class="btn" @click="openAgent(selectedIds[0])">查看详情</button>
              <button class="btn ghost" @click="openLibrary(selectedIds[0])">选择参考</button>
              <button class="btn ghost" @click="clearSelection">清除选择</button>
            </div>

            <p class="hint" style="position: absolute; left: 14px; bottom: 10px; z-index: 4">
              拖动连线 = 发起一次主题 Chat 或 Mail；位置只保存布局，不改团队关系。右键或卡片右上角可打开 Libraries。
            </p>
          </div>
        </div>
      </template>

      <ChatView
        v-else-if="tab === 'chat'"
        ref="chatRef"
        :project="project"
        :initial-room="initialChatRoom"
        @new-discussion="openCollab({ provider: '', receiver: '', mode: 'chat', remind: true })"
        @board="tab = 'board'"
      />

      <ProjectOverview
        v-else
        :project="project"
        :fallback-index="dashboard?.index"
        :fallback-team="dashboard?.team?.body"
      />

      <PersonDrawer
        :agent="drawerAgent"
        @close="drawerId = ''"
        @library="openLibrary"
        @collaborate="fromDrawer"
      />

      <LibraryPanel
        :open="libraryOpen"
        :agent-id="libraryAgent"
        :agent-name="libraryAgentSummary?.name || libraryAgent || ''"
        :examples="examples"
        @close="libraryOpen = false"
        @attach="attachReference"
        @send="sendReference"
      />

      <CollaborationDialog
        :open="collabOpen"
        :initial="collabInitial"
        :agents="agents"
        :project="project"
        @close="collabOpen = false"
        @completed="completed"
        @open-room="openRoom"
      />
    </main>
  </div>
</template>
