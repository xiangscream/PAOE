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
import { canStartCollaboration, displayNumber } from './state/team'

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
const hasSavedLayout = ref(false)
const saving = ref('')
const saveError = ref('')
let pendingSave: { project: string; layout: BoardLayout } | null = null
let failedSave: { project: string; layout: BoardLayout } | null = null
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
const collabRef = ref<InstanceType<typeof CollaborationDialog> | null>(null)
const attachingReference = ref(false)
const resetDialog = ref<HTMLDialogElement | null>(null)
const initialChatRoom = ref('')
const locate = ref('')
let savingQueue=Promise.resolve()
let loadGeneration = 0

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
  const generation=++loadGeneration
  loading.value = true
  error.value = ''
  notice.value = ''
  try {
    const initial = !projects.value.length ? await loadProjects() : null
    if(initial && !initial.projects.some(item=>item.id===target))target=initial.project
    const data = initial && initial.project===target ? initial : await api.dashboard(target)
    if(generation!==loadGeneration)return
    projects.value=data.projects
    dashboard.value = data
    project.value = data.project || target
    localStorage.setItem('poe.project', project.value)
    if(!project.value) {
      selectedIds.value=[]
      layout.value={nodes:{},viewport:{...DEFAULT_VIEWPORT}}
      hasSavedLayout.value=false
      notice.value='尚未登记项目。接入项目后，刷新即可开始使用。'
      return
    }
    let saved: BoardLayout | null = null
    let hasLayout = false
    try {
      const response = await api.getLayout(project.value)
      if(generation!==loadGeneration)return
      saved = response.layout || null
      hasLayout = !!saved && Object.keys(saved.nodes).length > 0
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
    layout.value = merged
    hasSavedLayout.value = hasLayout
    await nextTick()
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
    if(generation!==loadGeneration)return
    error.value = problem instanceof ApiError ? problem.message : String(problem)
  } finally {
    if(generation===loadGeneration)loading.value = false
  }
}

function queueSave(next: BoardLayout) {
  layout.value = next
  if (!layoutSupported.value) {
    saving.value = '未保存（布局接口不可用）'
    return
  }
  const owner = project.value
  const job = { project: owner, layout: next }
  pendingSave = job
  saving.value = '保存中…'
  if(failedSave?.project===owner){failedSave=null;saveError.value=''}
  savingQueue=savingQueue.then(()=>flushSave(job))
}

async function flushSave(job=pendingSave) {
  if (!job) return
  try {
    await api.saveLayout(job.project, job.layout)
    if (pendingSave === job) {
      pendingSave = null
      if (project.value === job.project) saving.value = '已保存布局'
    }
    if(failedSave===job){failedSave=null;saveError.value=''}
  } catch (problem) {
    const message = problem instanceof ApiError ? problem.message : String(problem)
    if (project.value === job.project) saving.value = '未保存'
    failedSave=job
    saveError.value = '项目 '+job.project+' 的布局未保存：' + message
  }
}

function retrySave() {
  const job=failedSave
  if (!job) return
  saving.value = '保存中…'
  pendingSave=job
  savingQueue=savingQueue.then(()=>flushSave(job))
}

function openChatRoomFromQuery() {
  const query=new URLSearchParams(location.search)
  const room=query.get('room')
  if (room)initialChatRoom.value=room
  tab.value=room || location.pathname.startsWith('/cat')?'chat':query.get('view')==='project'?'project':'board'
}

function changeProject() {
  initialChatRoom.value = ''
  const url = new URL(location.href)
  url.searchParams.delete('room')
  history.replaceState(null, '', url)
  void load(project.value)
}

function onNodeContext(payload: { id: string }) {
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
  attachingReference.value = false
  libraryAgent.value = id
  libraryOpen.value = true
}

function chooseCollaborationReference(id: string) {
  openLibrary(id)
  attachingReference.value = true
}

function openCollab(draft: Partial<CollaborationDraft> = {}) {
  if(!project.value){notice.value='请先接入一个项目，再邀请同事协作。';return}
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
  openCollab({ provider: chosen[0].id, receiver: chosen[1].id, participants:chosen.map(agent=>agent.id), mode: 'chat', remind: true })
}

function fromDrawer(id: string) {
  openCollab({ provider: '', receiver: id, mode: 'chat', remind: true })
}

function attachReference(item: LibraryItem) {
  libraryOpen.value = false
  if (attachingReference.value) {
    collabRef.value?.attachReference({title:item.title || item.id,path:item.path || '',kind:item.kind,id:item.id})
    return
  }
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
  boardRef.value?.clearEdges()
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
  resetDialog.value?.showModal()
}

async function restoreLayout() {
  await boardRef.value?.resetLayout()
  resetDialog.value?.close()
}

function clearSelection() {
  selectedIds.value = []
  boardRef.value?.select([])
}

watch(theme, value => applyTheme(value))
watch(tab, value=>{
  const url=new URL(location.href)
  url.pathname=value==='chat'?'/cat':'/'
  url.searchParams.delete('view')
  if(value==='chat') {
    document.title='CAT · PAOE'
    if(initialChatRoom.value)url.searchParams.set('room',initialChatRoom.value)
    else url.searchParams.delete('room')
  } else {
    url.searchParams.delete('room')
    if(value==='project')url.searchParams.set('view','project')
    document.title=(value==='board'?'团队画板':'项目概览')+' · PAOE'
  }
  history.replaceState(null,'',url)
})

onMounted(() => {
  applyTheme(theme.value)
  openChatRoomFromQuery()
  void load()
})
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand"><span class="brand-symbol">P</span><span>PAOE<small>本地协作空间</small></span></div>
      <select v-model="project" class="btn project-select" :disabled="collabOpen || libraryOpen" aria-label="选择项目" @change="changeProject">
        <option v-for="item in projects" :key="item.id" :value="item.id">{{ item.id }} {{ item.name || '' }}</option>
      </select>
      <nav class="nav-tabs" aria-label="主导航">
        <button :class="{ on: tab === 'board' }" @click="tab = 'board'">团队画板</button>
        <button :class="{ on: tab === 'chat' }" @click="tab = 'chat'">讨论</button>
        <button :class="{ on: tab === 'project' }" :disabled="!project" @click="tab = 'project'">项目概览</button>
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
            <div class="board-toolbar">
              <div class="board-title"><span>TEAM / {{ project }}</span><h1>团队画板<small>{{ agents.length }} 位同事</small></h1></div>
              <div class="board-tools">
                <form class="member-search" @submit.prevent="locatePerson"><input v-model="locate" aria-label="搜索成员或员工号" placeholder="搜索成员、职责…" /><button title="定位成员" aria-label="定位成员" type="submit">⌕</button></form>
                <button class="btn ghost" @click="boardRef?.fit()">适应画布</button>
                <button class="btn ghost" :disabled="loading || !agents.length" @click="resetBoard">恢复布局</button>
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
              @node-context="onNodeContext"
              @connect="fromConnection"
              @save="queueSave"
              @selection-change="onSelectionChange"
            />
            <div v-else-if="loading" class="hint" style="padding: 40px">读取项目团队…</div>
            <div v-else class="empty-board"><h2>团队还没有成员</h2><p>准备好项目与同事的原件后，刷新工作台即可查看。</p><button class="btn" @click="load(project)">刷新团队</button></div>
            </div>

            <div v-if="selectedIds.length" class="action-bar">
              <strong>{{ selectedIds.length }} 位已选</strong>
              <button v-if="canCollaborate" class="btn primary" @click="fromSelection">围绕主题协作</button>
              <button class="btn" @click="openAgent(selectedIds[0])">查看详情</button>
              <button class="btn ghost" @click="openLibrary(selectedIds[0])">选择参考</button>
              <button class="btn ghost" @click="clearSelection">清除选择</button>
            </div>

            <p class="board-help">
              拖动同事之间的连线，围绕一个主题开始协作。<span>Ctrl / ⌘ 多选 · 右键选参考</span>
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
        @room-selected="initialChatRoom = $event"
      />

      <ProjectOverview
        v-else
        :project="project"
      />

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
        @choose-reference="chooseCollaborationReference"
        @completed="completed"
        @open-room="openRoom"
      />
      <dialog ref="resetDialog" class="modal reset-layout-dialog" aria-labelledby="reset-layout-title">
        <section class="modal-box">
          <h2 id="reset-layout-title">恢复默认布局</h2>
          <p>恢复本项目的默认卡片位置与缩放。</p>
          <div class="modal-action">
            <button class="btn" @click="resetDialog?.close()">取消</button>
            <button class="btn primary" @click="restoreLayout">确认恢复</button>
          </div>
        </section>
        <form method="dialog" class="modal-backdrop"><button aria-label="关闭布局确认">关闭</button></form>
      </dialog>
    </main>
  </div>
</template>
