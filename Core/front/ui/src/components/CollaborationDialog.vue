<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import type { AgentSummary, CollabMode, CollabResult, CollabState } from '../types'
import type { CollaborationDraft, Reference } from '../state/collab'
import { buildBody, canResubmit, createMessageId, outcomeOf, payloadFor, validateDraft } from '../state/collab'

const props = defineProps<{
  open: boolean
  initial: CollaborationDraft
  agents: AgentSummary[]
  project: string
}>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'completed', result: CollabResult): void
  (e: 'open-room', id: string): void
  (e: 'choose-reference', id: string): void
}>()

interface SavedSession {
  phase: 'draft' | 'submitting' | 'settled'
  project: string
  draft: CollaborationDraft
  messageId: string
  state: CollabState | ''
  text: string
  result: CollabResult | null
  endedRequests: EndedRequest[]
}

interface EndedRequest {
  messageId: string
  topic: string
  mode: CollabMode
  roomId?: string
}

const draft = ref<CollaborationDraft>({ ...props.initial })
const messageId = ref(createMessageId())
const state = ref<CollabState | ''>('')
const text = ref('')
const submitting = ref(false)
const checking = ref(false)
const storageError = ref('')
const lastResult = ref<CollabResult | null>(null)
const restored = ref(false)
const resumedRoomId = ref('')
const ownerProject = ref(props.project)
const endedRequests = ref<EndedRequest[]>([])
const endingWaiting = ref(false)

const contactable = computed(() => props.agents.filter(agent => agent.can_contact !== false && agent.ok !== false))
const otherParticipants=computed(()=>(draft.value.participants || []).filter(id=>id!==draft.value.provider && id!==draft.value.receiver))
const locked = computed(() => submitting.value || checking.value || ['saved', 'unknown', 'partial'].includes(state.value) || restored.value)
const validation = computed(() => {
  const invalid=validateDraft(draft.value)
  if(invalid)return invalid
  if(!contactable.value.some(agent=>agent.id===draft.value.receiver))return '请选择可联系的接收方。'
  if(draft.value.provider && draft.value.provider!=='human' && !contactable.value.some(agent=>agent.id===draft.value.provider))return '请选择可联系的提供方。'
  if(otherParticipants.value.some(id=>!contactable.value.some(agent=>agent.id===id)))return '其他参与者中有不可联系的同事，请移除后继续。'
  return ''
})
const preview = computed(() => buildBody(draft.value))
const canSubmit = computed(() => !validation.value && !storageError.value && !locked.value && canResubmit(state.value))
const canContinuePartial = computed(
  () => state.value === 'partial' && !!lastResult.value?.room_id && !submitting.value && !checking.value,
)
const storageKey = computed(() => 'poe.collab.' + ownerProject.value)

function saveSession(phase: SavedSession['phase']): boolean {
  try {
    const value: SavedSession = {
      phase,
      project: ownerProject.value,
      draft: draft.value,
      messageId: messageId.value,
      state: state.value,
      text: text.value,
      result: lastResult.value,
      endedRequests: endedRequests.value,
    }
    localStorage.setItem(storageKey.value, JSON.stringify(value))
    storageError.value = ''
    return true
  } catch (problem) {
    storageError.value = '本地保存失败：' + String((problem as Error)?.message || problem) + '。请先处理存储，再提交。'
    return false
  }
}

function loadSession(): SavedSession | null | undefined {
  try {
    const raw = localStorage.getItem(storageKey.value)
    if (!raw) return null
    const value = JSON.parse(raw) as SavedSession
    if (value.project !== ownerProject.value) throw new Error('请求所属项目与当前项目不一致')
    return value
  } catch (problem) {
    storageError.value = '未能恢复原请求：' + String(problem)
    return undefined
  }
}

function resetTo(value: CollaborationDraft) {
  draft.value = {
    ...value,
    provider: value.mode === 'chat' && value.provider === 'human' ? '' : value.provider,
    reference: value.reference || null,
  }
  messageId.value = createMessageId()
  state.value = ''
  text.value = ''
  lastResult.value = null
  restored.value = false
  resumedRoomId.value = ''
  endingWaiting.value = false
  saveSession('draft')
}

function restoreOrReset() {
  if (submitting.value) return
  ownerProject.value = props.project
  const saved = loadSession()
  if (saved === undefined) return
  endedRequests.value = saved?.endedRequests || []
  endingWaiting.value = false
  const unfinished = saved && saved.project === props.project &&
    (saved.phase === 'submitting' || saved.state === 'unknown' || saved.state === 'partial')
  if (unfinished) {
    draft.value = saved.draft
    messageId.value = saved.messageId
    state.value = saved.phase !== 'submitting' && saved.state === 'partial' ? 'partial' : 'unknown'
    text.value = saved.text || '上次提交的结果未确认。请先核对原记录；核对前不会自动重发。'
    lastResult.value = saved.result
    restored.value = true
    resumedRoomId.value = saved.result?.room_id || ''
    return
  }
  resetTo(props.initial)
}

function label(agent: AgentSummary): string {
  const number = agent.number || agent.id
  const name = agent.name && agent.name !== agent.id ? agent.name : ''
  return name ? `${number} · ${name}` : number
}

function swap() {
  if (locked.value) return
  const provider = draft.value.provider
  draft.value.provider = draft.value.receiver
  draft.value.receiver = provider
  saveSession('draft')
}

function setMode(mode: CollabMode) {
  if (locked.value) return
  draft.value.mode = mode
  if (mode === 'chat' && draft.value.provider === 'human') draft.value.provider = ''
  saveSession('draft')
}

function close() {
  if (submitting.value || checking.value) return
  if (!submitting.value) saveSession(restored.value ? 'settled' : 'draft')
  emit('close')
}

async function submit(roomId = '') {
  if (roomId ? !canContinuePartial.value : !canSubmit.value) return
  if (state.value === 'failed') messageId.value = createMessageId()
  const payload = payloadFor(draft.value, ownerProject.value, messageId.value, roomId)
  if (!saveSession('submitting')) return
  submitting.value = true
  state.value = ''
  text.value = '正在发起协作…'
  try {
    const result = await api.collaborate(payload)
    lastResult.value = result
    const outcome = outcomeOf(result)
    state.value = outcome.state
    text.value = outcome.text
    if (outcome.state === 'saved' || outcome.state === 'partial') emit('completed', result)
  } catch (problem) {
    const outcome = outcomeOf(null, problem)
    state.value = outcome.state
    text.value = outcome.text
  } finally {
    submitting.value = false
    saveSession(state.value === 'unknown' ? 'submitting' : 'settled')
  }
}

async function continuePartial() {
  if (!canContinuePartial.value || !lastResult.value?.room_id) return
  resumedRoomId.value = lastResult.value.room_id
  await submit(lastResult.value.room_id)
}

async function check() {
  checking.value = true
  try {
    const result = await api.collaborationFact(ownerProject.value, draft.value.mode, messageId.value, lastResult.value?.room_id)
    if (result.state === 'saved') {
      lastResult.value = { ...lastResult.value, ...result, state: 'saved' }
      state.value = 'saved'
      text.value = '已核到原记录：请求已保存。提醒与接手仍以原回执为准。'
      restored.value = false
      emit('completed', lastResult.value)
    } else if (result.state === 'not_found') {
      text.value = '暂未读到原记录。保留本次请求，稍后再核对，不自动重发。'
    } else {
      text.value = '核对尚未完成，请稍后再查。原请求继续保留。'
    }
  } catch (problem) {
    text.value = '核对未完成：' + String((problem as Error)?.message || problem)
  } finally {
    checking.value = false
    saveSession('settled')
  }
}

function startNew() {
  resetTo({ ...draft.value, topic: '', note: '', reference: null })
}

function endWaiting() {
  if (state.value !== 'unknown' || submitting.value || checking.value) return
  endedRequests.value.push({ messageId: messageId.value, topic: draft.value.topic, mode: draft.value.mode, roomId: lastResult.value?.room_id })
  startNew()
}

function attachReference(reference: Reference) {
  if (locked.value) return
  draft.value.reference = reference
}
defineExpose({ attachReference })

watch(() => props.open, (open) => {
  if (open) restoreOrReset()
})
watch(draft, () => {
  if (!locked.value) saveSession('draft')
}, { deep: true })
onMounted(() => {
  if (props.open) restoreOrReset()
})
</script>

<template>
  <div v-show="props.open" class="panel" role="dialog" aria-modal="true" aria-label="发起主题协作">
    <header>
      <div>
        <strong>发起主题协作</strong>
        <div class="hint">提交前可见正文与去向；位置与连线不改团队关系。</div>
      </div>
      <span class="spacer"></span>
      <button class="btn ghost" :disabled="submitting" @click="close">关闭</button>
    </header>
    <div class="body">
      <div v-if="restored" class="banner">
        已恢复未完成的请求。可核对原记录，或明确结束本地等待并保留原编号；不会自动重发。
      </div>
      <div v-if="storageError" class="banner error">{{ storageError }}</div>

      <div class="row" style="align-items: flex-end">
        <div class="field" style="flex: 1">
          <label for="provider">提供方</label>
          <select id="provider" v-model="draft.provider" :disabled="locked">
            <option value="" disabled>选择同事</option>
            <option v-if="draft.mode === 'mail'" value="human">Human · 我提供</option>
            <option v-for="agent in contactable" :key="agent.id" :value="agent.id">{{ label(agent) }}</option>
          </select>
        </div>
        <button class="btn" title="交换方向" :disabled="locked" @click="swap">⇄</button>
        <div class="field" style="flex: 1">
          <label for="receiver">接收方</label>
          <select id="receiver" v-model="draft.receiver" :disabled="locked">
            <option value="" disabled>选择同事</option>
            <option v-for="agent in contactable" :key="agent.id" :value="agent.id">{{ label(agent) }}</option>
          </select>
        </div>
      </div>

      <div class="field">
        <label for="topic">主题（必填）</label>
        <input id="topic" v-model="draft.topic" maxlength="120" :disabled="locked" placeholder="这次补充什么？" />
      </div>
      <div v-if="otherParticipants.length" class="field">
        <label>其他参与者</label>
        <div class="row"><span v-for="id in otherParticipants" :key="id" class="participant-chip">
          {{ label(props.agents.find(agent=>agent.id===id) || {id}) }}
          <button type="button" :disabled="locked" :aria-label="'移除参与者 ' + id" @click="draft.participants=draft.participants?.filter(item=>item!==id)">×</button>
        </span></div>
      </div>

      <div class="field">
        <label>方式</label>
        <div class="row">
          <label class="row" style="gap: 4px">
            <input type="radio" :checked="draft.mode === 'chat'" :disabled="locked" @change="setMode('chat')" /> 临时 Chat
          </label>
          <label class="row" style="gap: 4px">
            <input type="radio" :checked="draft.mode === 'mail'" :disabled="locked" @change="setMode('mail')" /> 邮件
          </label>
          <label class="row" style="gap: 4px">
            <input v-model="draft.remind" type="checkbox" :disabled="locked" /> 同时提醒一次
          </label>
        </div>
        <p class="hint">
          {{ draft.mode === 'chat' ? 'Chat 会建立普通 CAT 房间，以 Human 身份发出主题首条消息。' : '邮件以 Human 身份留一封主题请求；Agent→Agent 时双方都收到。' }}
        </p>
      </div>

      <div class="field">
        <label for="note">补充说明</label>
        <textarea id="note" v-model="draft.note" rows="4" :disabled="locked" placeholder="可选：背景、需要对方接什么、参考路径…"></textarea>
      </div>

      <div v-if="draft.reference" class="card">
        <h3>参考</h3>
        <p>{{ draft.reference.title }}</p>
        <p class="hint">{{ draft.reference.path }}</p>
        <button v-if="!locked" class="btn ghost" @click="draft.reference = null">移除参考</button>
      </div>
      <button v-if="!locked" class="btn ghost add-reference" @click="emit('choose-reference', draft.receiver)">＋ 从参考库添加资料</button>

      <div class="card">
        <h3>提交预览</h3>
        <pre class="mono" style="max-height: 28vh; overflow: auto">{{ preview }}</pre>
      </div>

      <p v-if="validation && !locked" class="hint">{{ validation }}</p>
      <p v-if="text" class="card" role="status" aria-live="polite" :class="{ error: state === 'failed' }">{{ text }}</p>

      <div class="row" style="margin-top: 10px">
        <button v-if="!locked || submitting" class="btn primary" :disabled="!canSubmit" @click="submit()">
          {{ submitting ? '提交中…' : '发起协作' }}
        </button>
        <button v-if="['unknown','partial'].includes(state) && !submitting" class="btn" :disabled="checking" @click="check">
          {{ checking ? '核对中…' : '核对原记录' }}
        </button>
        <button v-if="canContinuePartial" class="btn primary" :disabled="submitting" @click="continuePartial">
          继续原房间
        </button>
        <button v-if="lastResult?.room_id" class="btn ghost" :disabled="submitting || checking" @click="emit('open-room', lastResult!.room_id!)">打开房间</button>
        <button v-if="state === 'saved' || state === 'failed'" class="btn ghost" @click="startNew">新建另一个请求</button>
        <button v-if="state === 'unknown' && !submitting" class="btn ghost" :disabled="checking" @click="endingWaiting = true">结束本地等待</button>
      </div>

      <section v-if="endingWaiting && state === 'unknown'" class="card" aria-label="结束协作等待">
        <p>原请求可能已保存，仍会保留编号。结束等待会清空本次主题和说明，服务器记录不会被撤销，也不会重发。</p>
        <div class="row"><button class="btn ghost" @click="endingWaiting = false">继续核对</button><button class="btn" :disabled="checking" @click="endWaiting">确认结束，开始新主题</button></div>
      </section>
      <details v-if="endedRequests.length" class="card">
        <summary>已结束等待的请求（{{ endedRequests.length }}）</summary>
        <p v-for="item in endedRequests" :key="item.messageId" style="overflow-wrap: anywhere">
          {{ item.topic }} · {{ item.mode }} · 保存结果仍未确认<br>请求编号：{{ item.messageId }}
          <button v-if="item.roomId" class="btn ghost" @click="emit('open-room', item.roomId)">查看原房间</button>
        </p>
      </details>

      <details v-if="messageId" class="hint" style="margin-top: 8px">
        <summary>请求详情</summary>
        <p>请求编号：{{ messageId }}</p>
        <p v-if="resumedRoomId">续用房间：{{ resumedRoomId }}</p>
      </details>
    </div>
  </div>
</template>
