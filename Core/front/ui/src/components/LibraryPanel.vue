<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, ApiError } from '../api'
import type { LibraryItem } from '../types'

const props = defineProps<{
  open: boolean
  agentId: string
  agentName: string
  examples: Record<string, LibraryItem[]>
}>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'attach', item: LibraryItem): void
  (e: 'send', item: LibraryItem): void
}>()

const kind = ref<'workflow' | 'skill' | 'tool'>('workflow')
const query = ref('')
const selected = ref<LibraryItem | null>(null)
const body = ref('')
const loading = ref(false)
const error = ref('')

const all = computed(() => props.examples?.[kind.value] || [])
const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return all.value
  return all.value.filter(item =>
    `${item.id} ${item.title || ''} ${item.path || ''} ${item.description || ''}`.toLowerCase().includes(q),
  )
})

async function preview(item: LibraryItem) {
  selected.value = item
  body.value = ''
  error.value = ''
  loading.value = true
  try {
    const data = await api.resource(item.kind, item.id)
    body.value = data.resource.body || ''
  } catch (problem) {
    error.value = problem instanceof ApiError ? problem.message : String(problem)
  } finally {
    loading.value = false
  }
}

watch(() => props.open, (open) => {
  if (open) {
    query.value = ''
    selected.value = null
    body.value = ''
    error.value = ''
  }
})
</script>

<template>
  <aside v-if="props.open" class="panel" aria-label="Libraries 选择器">
    <header>
      <div>
        <strong>选择参考</strong>
        <div class="hint">给 {{ props.agentName }} · 浏览不发送，也不改变长期能力</div>
      </div>
      <span class="spacer"></span>
      <button class="btn ghost" @click="emit('close')">关闭</button>
    </header>
    <div class="body" style="display: grid; gap: 10px; grid-template-rows: auto 1fr;">
      <div class="row">
        <select v-model="kind" class="btn" aria-label="资源类型">
          <option value="workflow">Workflow</option>
          <option value="skill">Skill</option>
          <option value="tool">Tool</option>
        </select>
        <input v-model="query" class="btn" style="flex: 1; min-width: 0" placeholder="搜索标题、用途或路径" />
        <span class="hint">{{ filtered.length }} 项</span>
      </div>
      <div style="display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 10px; min-height: 0">
        <div style="overflow: auto; display: grid; gap: 6px; align-content: start">
          <p v-if="!filtered.length" class="hint">没有匹配项。</p>
          <button
            v-for="item in filtered"
            :key="item.id + item.kind"
            class="list-item"
            :class="{ on: selected?.id === item.id }"
            @click="preview(item)"
          >
            <strong>{{ item.title || item.id }}</strong>
            <div class="hint">{{ item.kind }} · {{ item.path }}</div>
          </button>
        </div>
        <div style="overflow: auto">
          <div v-if="!selected" class="hint">选择左侧一项查看用途与原文。</div>
          <div v-else class="card">
            <h3>{{ selected.title || selected.id }}</h3>
            <p class="hint">{{ selected.path }}</p>
            <p v-if="selected.description">{{ selected.description }}</p>
            <p v-if="loading" class="hint">读取原文…</p>
            <p v-else-if="error" class="muted">{{ error }}</p>
            <pre v-else class="mono" style="max-height: 42vh; overflow: auto">{{ body }}</pre>
            <div class="row" style="margin-top: 10px">
              <button class="btn primary" @click="emit('attach', selected)">附到本次协作</button>
              <button class="btn" @click="emit('send', selected)">单独发参考信</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </aside>
</template>
