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

const draft = ref<CollaborationDraft>({ ...props.initial })
const messageId = ref(createMessageId())
const state = ref<CollabState | ''>('')
const text = ref('')
const submitting = ref(false)
const checking = ref(false)
const lastResult = ref<CollabResult | null>(null)
const restored = ref(false)

const contactable = computed(() => props.agents.filter(agent => agent.can_contact !== false && agent.ok !== false))
const locked = computed(() => state.value === 'unknown' || state.value === 'partial')
const validation = computed(() => validateDraft(draft.value))
const preview = computed(() => buildBody(draft.value))
const canSubmit = computed(() => !validation.value && !submitting.value && canResubmit(state.value))

const storageKey = computed(() => 'poe.collab.' + props.project)

interface SavedSession {
  draft: CollaborationDraft
  messageId: string
  state: CollabState | ''
  text: string
  result: CollabResult | null
}

function saveSession() {
  try {
    const value: SavedSession = {
      draft: draft.value,
      messageId: messageId.value,
      state: state.value,
      text: text.value,
      result: lastResult.value,
    }
    localStorage.setItem(storageKey.value, JSON.stringify(value))
  } catch {
    /* ignore */
  }
}

function loadSession(): SavedSession | null {
  try {
    const raw = localStorage.getItem(storageKey.value)
    return raw ? (JSON.parse(raw) as SavedSession) : null
  } catch {
    return null
  }
}

function resetTo(draftValue: CollaborationDraft) {
  draft.value = { ...draftValue, reference: draftValue.reference || null }
  messageId.value = createMessageId()
  state.value = ''
  text.value = ''
  lastResult.value = null
  saveSession()
}

function restoreOrReset() {
  const saved = loadSession()
  if (saved && (saved.state === 'unknown' || saved.state === 'partial') && saved.messageId) {
    draft.value = saved.draft
    messageId.value = saved.messageId
    state.value = saved.state
    text.value = saved.text
    lastResult.value = saved.result
    restored.value = true
    return
  }
  restored.value = false
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
  saveSession()
}

function setMode(mode: CollabMode) {
  if (locked.value) return
  draft.value.mode = mode
  saveSession()
}

function close() {
  saveSession()
  emit('close')
}

async function submit() {
  if (!canSubmit.value) return
  submitting.value = true
  state.value = ''
  text.value = ''
  const payload = payloadFor(draft.value, props.project, messageId.value)
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
    saveSession()
  }
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
      emit('completed', result)
    } else if (result.state === 'not_found') {
      text.value = '暂未读到原记录。保留本次请求，稍后再核对，不自动重发。'
    } else {
      state.value = outcome.state
      text.value = '核对结果：' + outcome.text
    }
  } catch (problem) {
    text.value = '核对未完成：' + String((problem as Error)?.message || problem)
  } finally {
    checking.value = false
    saveSession()
  }
}

watch(() => props.open, (open) => {
  if (open) restoreOrReset()
})
watch(draft, () => saveSession(), { deep: true })
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
      <button class="btn ghost" @click="close">关闭</button>
    </header>
    <div class="body">
      <div v-if="restored" class="banner">
        已恢复未完成的协作请求（{{ messageId }}）。请先核对原记录；核对前不能改对象或方式，也不会自动重发。
      </div>

      <div class="row" style="align-items: flex-end">
        <div class="field" style="flex: 1">
          <label for="provider">提供方</label>
          <select id="provider" v-model="draft.provider" :disabled="locked">
            <option value="human">Human（我提供）</option>
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
        <button class="btn primary" :disabled="!canSubmit" @click="submit">
          {{ submitting ? '提交中…' : '发起协作' }}
        </button>
        <button v-if="locked" class="btn" :disabled="checking" @click="check">
          {{ checking ? '核对中…' : '核对原记录' }}
        </button>
        <button v-if="lastResult?.room_id" class="btn ghost" @click="emit('open-room', lastResult!.room_id!)">打开房间</button>
        <span class="hint">请求编号：{{ messageId }}</span>
      </div>
    </div>
  </div>
</template>
