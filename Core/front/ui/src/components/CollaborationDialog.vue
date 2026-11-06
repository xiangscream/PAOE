<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import type { AgentSummary, CollabMode, CollabResult, CollabState } from '../types'
import type { CollaborationDraft } from '../state/collab'
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
}>()

interface SavedSession {
  phase: 'draft' | 'submitting' | 'settled'
  project: string
  draft: CollaborationDraft
  messageId: string
  state: CollabState | ''
  text: string
  result: CollabResult | null
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

const contactable = computed(() => props.agents.filter(agent => agent.can_contact !== false && agent.ok !== false))
const locked = computed(() => submitting.value || state.value === 'unknown' || state.value === 'partial' || restored.value)
const validation = computed(() => validateDraft(draft.value))
const preview = computed(() => buildBody(draft.value))
const canSubmit = computed(() => !validation.value && !submitting.value && canResubmit(state.value) && !restored.value)
const canContinuePartial = computed(
  () => state.value === 'partial' && !!lastResult.value?.room_id && !!lastResult.value?.message_id && !submitting.value,
)
const storageKey = computed(() => 'poe.collab.' + props.project)

function saveSession(phase: SavedSession['phase']): boolean {
  try {
    const value: SavedSession = {
      phase,
      project: props.project,
      draft: draft.value,
      messageId: messageId.value,
      state: state.value,
      text: text.value,
      result: lastResult.value,
    }
    localStorage.setItem(storageKey.value, JSON.stringify(value))
    storageError.value = ''
    return true
  } catch (problem) {
    storageError.value = '本地保存失败：' + String((problem as Error)?.message || problem) + '。请先处理存储，再提交。'
    return false
  }
}

function loadSession(): SavedSession | null {
  try {
    const raw = localStorage.getItem(storageKey.value)
    if (!raw) return null
    const value = JSON.parse(raw) as SavedSession
    if (value.project !== props.project) return null
    return value
  } catch {
    return null
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
  saveSession('draft')
}

function restoreOrReset() {
  const saved = loadSession()
  const unfinished = saved && saved.project === props.project &&
    (saved.phase === 'submitting' || saved.state === 'unknown' || saved.state === 'partial')
  if (unfinished) {
    draft.value = saved.draft
    messageId.value = saved.messageId
    state.value = saved.state === 'partial' ? 'partial' : 'unknown'
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
  if (!submitting.value) saveSession(restored.value ? 'settled' : 'draft')
  emit('close')
}

async function submit(roomId = '') {
  if (!canSubmit.value && !roomId) return
  if (!saveSession('submitting')) return
  if (state.value === 'failed') messageId.value = createMessageId()
  submitting.value = true
  state.value = ''
  text.value = ''
  const payload = payloadFor(draft.value, props.project, messageId.value, roomId)
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
    const result = await api.collaborationFact(props.project, draft.value.mode, messageId.value, lastResult.value?.room_id)
    lastResult.value = result
    const outcome = outcomeOf(result)
    if (outcome.state === 'saved') {
      state.value = 'saved'
      text.value = '已核到原记录：请求已保存。提醒与接手仍以原回执为准。'
      restored.value = false
      emit('completed', result)
    } else if (result.state === 'not_found') {
      text.value = '暂未读到原记录。保留本次请求，稍后再核对，不自动重发。'
    } else {
      state.value = outcome.state
      text.value = outcome.text
    }
  } catch (problem) {
    text.value = '核对未完成：' + String((problem as Error)?.message || problem)
  } finally {
    checking.value = false
    saveSession(state.value === 'unknown' || state.value === 'partial' ? 'submitting' : 'settled')
  }
}

function startNew() {
  resetTo({ ...draft.value, topic: '', note: '', reference: null })
}

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
        已恢复未完成的请求。请先核对原记录；核对前不能改对象或方式，也不会自动重发。
      </div>
      <div v-if="storageError" class="banner error">{{ storageError }}</div>

      <div class="row" style="align-items: flex-end">
        <div class="field" style="flex: 1">
          <label for="provider">提供方</label>
          <select id="provider" v-model="draft.provider" :disabled="locked">
            <option value="" disabled>选择同事</option>
            <option v-for="agent in contactable" :key="agent.id" :value="agent.id">{{ label(agent) }}</option>
          </select>
          <span v-if="draft.mode === 'chat'" class="hint">Chat 由同事之间接续，Human 只作为发言人。</span>
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

      <div class="card">
        <h3>提交预览</h3>
        <pre class="mono" style="max-height: 28vh; overflow: auto">{{ preview }}</pre>
      </div>

      <p v-if="validation && !locked" class="hint">{{ validation }}</p>
      <p v-if="text" class="card" :class="{ error: state === 'failed' }">{{ text }}</p>

      <div class="row" style="margin-top: 10px">
        <button v-if="!locked" class="btn primary" :disabled="!canSubmit" @click="submit()">
          {{ submitting ? '提交中…' : '发起协作' }}
        </button>
        <button v-if="locked && !submitting" class="btn" :disabled="checking" @click="check">
          {{ checking ? '核对中…' : '核对原记录' }}
        </button>
        <button v-if="canContinuePartial" class="btn primary" :disabled="submitting" @click="continuePartial">
          继续原房间
        </button>
        <button v-if="lastResult?.room_id" class="btn ghost" @click="emit('open-room', lastResult!.room_id!)">打开房间</button>
        <button v-if="state === 'saved' || state === 'failed'" class="btn ghost" @click="startNew">新建另一个请求</button>
      </div>

      <details v-if="messageId" class="hint" style="margin-top: 8px">
        <summary>请求详情</summary>
        <p>请求编号：{{ messageId }}</p>
        <p v-if="resumedRoomId">续用房间：{{ resumedRoomId }}</p>
      </details>
    </div>
  </div>
</template>
