<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, ApiError } from '../api'
import type { LibraryItem } from '../types'
import DocView from './DocView.vue'

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
const copied = ref('')
let token = 0

const all = computed(() => props.examples?.[kind.value] || [])
const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return all.value
  return all.value.filter(item =>
    `${item.id} ${item.title || ''} ${item.path || ''} ${item.description || ''}`.toLowerCase().includes(q),
  )
})

async function preview(item: LibraryItem) {
  const request = ++token
  selected.value = item
  body.value = ''
  error.value = ''
  loading.value = true
  try {
    const data = await api.resource(item.kind, item.id)
    if (request !== token) return
    body.value = data.resource.body || ''
  } catch (problem) {
    if (request !== token) return
    error.value = problem instanceof ApiError ? problem.message : String(problem)
  } finally {
    if (request === token) loading.value = false
  }
}

function setKind(value: 'workflow' | 'skill' | 'tool') {
  if (kind.value === value) return
  kind.value = value
  selected.value = null
  body.value = ''
  error.value = ''
  query.value = ''
  loading.value = false
  token += 1
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

watch(() => props.open, (open) => {
  if (open) {
    query.value = ''
    selected.value = null
    body.value = ''
    error.value = ''
    copied.value = ''
    token += 1
  }
})
</script>

<template>
  <aside v-if="props.open" class="panel library-panel" aria-label="Libraries 选择器">
    <header>
      <div>
        <strong>选择参考</strong>
        <div class="hint">给 {{ props.agentName }} · 浏览与预览不会发送，也不改变长期能力</div>
      </div>
      <span class="spacer"></span>
      <button class="btn ghost" @click="emit('close')">关闭</button>
    </header>

    <div class="body library-body">
      <div class="row library-filter">
        <button class="btn" :class="{ primary: kind === 'workflow' }" @click="setKind('workflow')">Workflow</button>
        <button class="btn" :class="{ primary: kind === 'skill' }" @click="setKind('skill')">Skill</button>
        <button class="btn" :class="{ primary: kind === 'tool' }" @click="setKind('tool')">Tool</button>
      </div>
      <div class="row">
        <input v-model="query" class="btn" style="flex: 1; min-width: 0" placeholder="搜索标题、用途或路径" />
        <span class="hint">{{ filtered.length }} 项</span>
      </div>

      <div class="library-grid">
        <div class="library-list">
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

        <div class="library-preview">
          <div v-if="!selected" class="hint">选择左侧一项查看用途与原文。</div>
          <template v-else>
            <div class="row">
              <div style="min-width: 0">
                <strong>{{ selected.title || selected.id }}</strong>
                <div class="hint">{{ selected.path }}</div>
              </div>
              <span class="spacer"></span>
              <button class="btn ghost" @click="copy(selected.path || selected.id)">复制路径</button>
            </div>
            <p v-if="copied" class="hint">{{ copied }}</p>
            <p v-if="selected.description" class="hint">{{ selected.description }}</p>
            <p v-if="loading" class="hint">读取原文…</p>
            <div v-else-if="error" class="card">
              <p class="muted">预览失败：{{ error }}</p>
              <p class="hint">尚未读到正文；原件位置：{{ selected.path }}</p>
              <button class="btn" @click="preview(selected)">重试</button>
            </div>
            <DocView v-else :body="body" :path="selected.path" @copy="copy" />
            <div class="row" style="margin-top: 8px">
              <button class="btn primary" @click="emit('attach', selected)">附到本次协作</button>
              <button class="btn" @click="emit('send', selected)">单独发参考信</button>
            </div>
          </template>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.library-body {
  display: grid;
  gap: 10px;
  grid-template-rows: auto auto minmax(0, 1fr);
  min-height: 0;
}

.library-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
  gap: 10px;
  min-height: 0;
  overflow: hidden;
}

.library-list {
  overflow: auto;
  display: grid;
  gap: 6px;
  align-content: start;
  min-height: 0;
}

.library-preview {
  overflow: auto;
  min-height: 0;
  display: grid;
  gap: 8px;
  align-content: start;
}

@media (max-width: 720px) {
  .library-grid {
    grid-template-columns: 1fr;
    overflow: auto;
  }

  .library-list,
  .library-preview {
    max-height: none;
  }
}
</style>
