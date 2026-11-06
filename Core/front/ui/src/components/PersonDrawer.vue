<script setup lang="ts">
import { ref, watch } from 'vue'
import { api, ApiError } from '../api'
import type { AgentDetail, AgentSummary } from '../types'
import { actionText, displayName, displayNumber, displayRole, isPaused, statusLabel } from '../state/team'

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

async function load(id: string) {
  loading.value = true
  error.value = ''
  detail.value = null
  showRaw.value = false
  try {
    detail.value = await api.agent(id)
  } catch (problem) {
    error.value = problem instanceof ApiError ? problem.message : String(problem)
  } finally {
    loading.value = false
  }
}

watch(() => props.agent?.id, (id) => {
  if (id) void load(id)
}, { immediate: true })
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
      <div v-if="loading" class="hint">读取工位…</div>
      <div v-else-if="error" class="card">
        <p class="muted">{{ error }}</p>
        <button class="btn" @click="props.agent && load(props.agent.id)">重试</button>
      </div>
      <div v-else-if="detail" class="list">
        <div v-if="isPaused(props.agent)" class="banner">
          该成员当前暂停或不可联系。下面仍显示原件内容，但不代表可以直接排任务。
        </div>
        <div class="row">
          <button class="btn primary" @click="emit('collaborate', props.agent!.id)">发起协作</button>
          <button class="btn" @click="emit('library', props.agent!.id)">选择参考</button>
          <button class="btn ghost" @click="showRaw = !showRaw">{{ showRaw ? '收起原文' : '查看 TODO 原文' }}</button>
        </div>
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
          <ul style="margin: 0; padding-left: 18px">
            <li v-for="(task, index) in detail.task_items.slice(0, 12)" :key="index">
              <span class="muted">{{ String((task as any)?.state || '') }}</span>
              {{ String((task as any)?.title || (task as any)?.id || '').slice(0, 120) }}
            </li>
          </ul>
        </section>
        <section v-if="detail.mails?.length" class="card">
          <h3>最近邮件</h3>
          <div v-for="mail in detail.mails.slice(0, 5)" :key="mail.name" class="list-item" style="cursor: default">
            <div class="hint">{{ mail.name }}</div>
            <div style="white-space: pre-wrap">{{ mail.preview.slice(0, 320) }}</div>
          </div>
        </section>
        <section v-if="detail.docs?.length" class="card">
          <h3>成果文档</h3>
          <div class="hint">{{ detail.docs.join(' · ') }}</div>
        </section>
        <section v-if="showRaw" class="card">
          <h3>TODO 原文</h3>
          <pre class="mono">{{ detail.todo }}</pre>
        </section>
        <p class="hint">原件：{{ detail.home_path || props.agent.id }} · 只读投影，修改仍在工位原件。</p>
      </div>
    </div>
  </aside>
</template>
