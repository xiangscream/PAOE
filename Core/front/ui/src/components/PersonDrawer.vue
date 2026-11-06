<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, ApiError } from '../api'
import type { AgentDetail, AgentSummary } from '../types'
import { actionText, displayName, displayNumber, displayRole, isPaused, statusLabel } from '../state/team'
import DocView from './DocView.vue'

const props = defineProps<{ agent: AgentSummary | null }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'library', id: string): void
  (e: 'collaborate', id: string): void
}>()

const detail = ref<AgentDetail | null>(null)
const loading = ref(false)
const error = ref('')
const showRaw = ref(false)
const docPath = ref('')
const docBody = ref('')
const docError = ref('')
const docLoading = ref(false)
const copied = ref('')
let token = 0
let docToken = 0

const contactable = computed(() => !!props.agent && props.agent.registered !== false && props.agent.ok !== false && props.agent.can_contact !== false && !isPaused(props.agent))

const TASK_STATES: Record<string, string> = {
  todo: '待办',
  doing: '进行中',
  waiting: '等待',
  done: '已完成',
  cancelled: '已取消',
  review: '待审阅',
}

function stateLabel(state: unknown): string {
  const key = String(state || '').toLowerCase()
  return TASK_STATES[key] || String(state || '未标注')
}

async function load(id: string) {
  const request = ++token
  loading.value = true
  error.value = ''
  detail.value = null
  showRaw.value = false
  docPath.value = ''
  docBody.value = ''
  docError.value = ''
  if (props.agent?.registered === false || props.agent?.ok === false) {
    loading.value = false
    return
  }
  try {
    const data = await api.agent(id)
    if (request !== token) return
    detail.value = data
  } catch (problem) {
    if (request !== token) return
    error.value = problem instanceof ApiError ? problem.message : String(problem)
  } finally {
    if (request === token) loading.value = false
  }
}

watch(() => props.agent?.id, (id) => {
  if (id) void load(id)
}, { immediate: true })

async function openDoc(path: string) {
  const project = detail.value?.project
  if (!project) return
  const request = ++docToken
  docLoading.value = true
  docError.value = ''
  docBody.value = ''
  docPath.value = path
  try {
    const data = await api.document(project, path)
    if (request !== docToken) return
    docBody.value = data.body || ''
    docPath.value = data.path || path
  } catch (problem) {
    if (request !== docToken) return
    docError.value = problem instanceof ApiError ? problem.message : String(problem)
  } finally {
    if (request === docToken) docLoading.value = false
  }
}

function closeDoc() {
  docPath.value = ''
  docBody.value = ''
  docError.value = ''
}

async function copy(path: string) {
  try {
    await navigator.clipboard.writeText(path)
    copied.value = '已复制：' + path
    setTimeout(() => { copied.value = '' }, 2000)
  } catch {
    copied.value = '复制失败，请手动选择：' + path
  }
}

function artifactOf(task: unknown): string {
  const value = task as Record<string, unknown>
  return String(value?.artifact_ref || value?.artifact || '')
}
</script>

<template>
  <aside v-if="props.agent" class="drawer" aria-label="工位详情">
    <header>
      <div style="min-width: 0">
        <strong>{{ displayName(props.agent) }}</strong>
        <span class="hint"> · {{ displayNumber(props.agent) }}</span>
        <div class="hint">{{ displayRole(props.agent) }} · {{ statusLabel(props.agent) }}</div>
      </div>
      <span class="spacer"></span>
      <button class="btn ghost" @click="emit('close')">关闭</button>
    </header>

    <div class="body">
      <div v-if="docPath" class="doc-panel">
        <div class="row" style="margin-bottom: 8px">
          <button class="btn ghost" @click="closeDoc">← 返回详情</button>
          <span class="hint">{{ docPath }}</span>
        </div>
        <p v-if="docLoading" class="hint">读取文档…</p>
        <div v-else-if="docError" class="card">
          <p class="muted">{{ docError }}</p>
          <p class="hint">原件位置：{{ docPath }}</p>
          <button class="btn" @click="copy(docPath)">复制路径</button>
        </div>
        <DocView v-else :body="docBody" :path="docPath" @copy="copy" />
      </div>

      <template v-else>
        <div v-if="props.agent.registered === false" class="banner">
          该成员尚未接入工位：展示 TEAM 登记信息，不请求不存在的工位文件，也不提供联系动作。
        </div>
        <div v-else-if="props.agent.ok === false" class="banner">
          工位不可读：{{ props.agent.error || '请检查登记路径或权限' }}。仍可查看 TEAM 说明和浏览参考。
        </div>
        <div v-else-if="isPaused(props.agent)" class="banner">
          该成员当前暂停或不可联系。下面仍显示原件内容，但不代表可以直接排任务。
        </div>

        <div class="row">
          <button class="btn primary" :disabled="!contactable" @click="emit('collaborate', props.agent!.id)">发起协作</button>
          <button class="btn" @click="emit('library', props.agent!.id)">选择参考</button>
          <button v-if="detail" class="btn ghost" @click="showRaw = !showRaw">{{ showRaw ? '收起 TODO 原文' : '查看 TODO 原文' }}</button>
        </div>

        <section class="card">
          <h3>职责</h3>
          <p>{{ displayRole(props.agent) }}</p>
          <p v-if="props.agent.member_status" class="hint">TEAM 状态：{{ props.agent.member_status }}</p>
        </section>

        <div v-if="loading" class="hint">读取工位…</div>
        <div v-else-if="error" class="card">
          <p class="muted">{{ error }}</p>
          <button class="btn" @click="props.agent && load(props.agent.id)">重试</button>
        </div>

        <template v-else-if="detail">
          <section class="card">
            <h3>当前目标</h3>
            <p>{{ detail.objective || '（无）' }}</p>
          </section>
          <section class="card">
            <h3>下一步</h3>
            <p>{{ actionText({ ...detail, id: props.agent!.id }) }}</p>
          </section>

          <section v-if="detail.task_items?.length" class="card">
            <h3>任务</h3>
            <ul class="task-list">
              <li v-for="(task, index) in detail.task_items.slice(0, 20)" :key="index">
                <span class="task-state" :data-state="String((task as any)?.state || '')">{{ stateLabel((task as any)?.state) }}</span>
                <span>{{ String((task as any)?.title || (task as any)?.id || '').slice(0, 140) }}</span>
                <button
                  v-if="artifactOf(task)"
                  class="btn ghost"
                  style="padding: 1px 6px"
                  @click="openDoc(artifactOf(task))"
                >成果</button>
              </li>
            </ul>
          </section>

          <section v-if="detail.docs?.length" class="card">
            <h3>成果文档</h3>
            <div class="row">
              <button v-for="doc in detail.docs.slice(0, 12)" :key="doc" class="btn ghost" @click="openDoc(doc)">{{ doc }}</button>
            </div>
            <p v-if="copied" class="hint">{{ copied }}</p>
          </section>

          <section v-if="detail.mails?.length" class="card">
            <h3>最近邮件</h3>
            <div v-for="mail in detail.mails.slice(0, 5)" :key="mail.name" class="mail-item">
              <div class="hint">{{ mail.name }}</div>
              <div style="white-space: pre-wrap">{{ mail.preview.slice(0, 320) }}</div>
            </div>
          </section>

          <section v-if="showRaw" class="card">
            <h3>TODO 原文</h3>
            <pre class="mono raw-todo">{{ detail.todo }}</pre>
          </section>

          <p class="hint">原件：{{ detail.home_path || props.agent.id }} · 只读投影，修改仍在工位原件。</p>
        </template>
      </template>
    </div>
  </aside>
</template>

<style scoped>
.doc-panel {
  min-width: 0;
}

.task-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 6px;
}

.task-list li {
  display: flex;
  gap: 6px;
  align-items: baseline;
  flex-wrap: wrap;
}

.task-state {
  flex: 0 0 auto;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 0 7px;
  font-size: 11px;
  color: var(--muted);
}

.task-state[data-state='doing'] {
  color: #0b7a5c;
  border-color: #9fd8c8;
}

.task-state[data-state='waiting'] {
  color: #8a5a00;
  border-color: #ead3a5;
}

.task-state[data-state='cancelled'] {
  color: #8a1f1f;
  border-color: #efc9c9;
}

.mail-item {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 6px;
}

.raw-todo {
  max-height: 46vh;
  overflow: auto;
}

@media (max-width: 560px) {
  .drawer {
    width: 100%;
  }
}
</style>
