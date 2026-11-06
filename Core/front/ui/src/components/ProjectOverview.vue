<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { api, ApiError } from '../api'
import DocView from './DocView.vue'
import { resolveDocPath } from '../lib/markdown'

const props = defineProps<{ project: string }>()

const which = ref<'INDEX.md' | 'TEAM.md'>('INDEX.md')
const currentPath = ref('INDEX.md')
const history = ref<string[]>([])
const body = ref('')
const loading = ref(false)
const error = ref('')
const notice = ref('')
const copied = ref('')
const blockedPath = ref('')
let token = 0

async function load(path: string, hash = '') {
  const request = ++token
  currentPath.value = path
  loading.value = true
  error.value = ''
  body.value = ''
  try {
    const data = await api.document(props.project, path)
    if (request !== token) return
    currentPath.value = data.path || path
    body.value = data.body || ''
  } catch (problem) {
    if (request !== token) return
    error.value = problem instanceof ApiError ? problem.message : String(problem)
  } finally {
    if (request === token) loading.value = false
  }
  await nextTick()
  if(hash && request === token)document.getElementById(hash)?.scrollIntoView({block:'start'})
}

function openRoot(entry: 'INDEX.md' | 'TEAM.md') {
  which.value = entry
  history.value = []
  notice.value = ''
  blockedPath.value = ''
  void load(entry)
}

function navigate(href: string) {
  const target = resolveDocPath(currentPath.value, href)
  if (target.kind === 'external') {
    window.open(target.path, '_blank', 'noopener,noreferrer')
    return
  }
  if (target.kind === 'anchor') return
  if (target.kind === 'absolute') {
    blockedPath.value = target.path
    notice.value = '项目外或非 Markdown 路径：' + target.path + '（可复制原件位置，不在网页直接打开）'
    return
  }
  history.value = [...history.value, currentPath.value]
  notice.value = ''
  void load(target.path, target.hash)
}

function back() {
  const previous = history.value.at(-1)
  if (!previous) return
  history.value = history.value.slice(0, -1)
  void load(previous)
}

async function copy(path: string) {
  try {
    await navigator.clipboard.writeText(path)
    copied.value = '已复制：' + path
    setTimeout(() => { if (copied.value.startsWith('已复制')) copied.value = '' }, 2200)
  } catch {
    copied.value = '复制失败，请手动选择路径：' + path
  }
}

watch(() => props.project, () => openRoot('INDEX.md'))

onMounted(() => openRoot('INDEX.md'))
</script>

<template>
  <div class="doc-page">
    <div class="doc-nav">
      <button class="btn" :class="{ primary: which === 'INDEX.md' }" @click="openRoot('INDEX.md')">项目 INDEX</button>
      <button class="btn" :class="{ primary: which === 'TEAM.md' }" @click="openRoot('TEAM.md')">TEAM</button>
      <button v-if="history.length" class="btn ghost" @click="back">← 上篇</button>
      <button class="btn ghost" @click="openRoot('INDEX.md')">项目入口</button>
      <span class="doc-crumb">{{ currentPath }}</span>
    </div>

    <p v-if="notice" class="doc-notice">
      {{ notice }}
      <button v-if="blockedPath" class="btn ghost" @click="copy(blockedPath)">复制路径</button>
    </p>
    <p v-if="copied" class="doc-notice">{{ copied }}</p>

    <p v-if="loading" class="hint">读取项目原文…</p>
    <div v-else-if="error" class="doc-error">
      <p>{{ error }}</p>
      <button class="btn" @click="load(currentPath)">重试</button>
    </div>
    <DocView
      v-else
      :body="body"
      :path="currentPath"
      @navigate="navigate"
      @copy="copy"
    />

    <p class="hint">只读本地原件；项目内 Markdown 相对链接可在本页继续阅读。修改仍在项目文件与 Git。</p>
  </div>
</template>

<style scoped>
.doc-page {
  height: 100%;
  overflow: auto;
  padding: 16px 20px 28px;
  display: grid;
  gap: 10px;
  align-content: start;
}

.doc-nav {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.doc-crumb {
  color: var(--muted);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.doc-notice {
  margin: 0;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  color: var(--ink);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.doc-error {
  border: 1px solid #efc9c9;
  background: #fff6f6;
  color: #8a1f1f;
  border-radius: 10px;
  padding: 12px 14px;
}

@media (max-width: 560px) {
  .doc-page {
    padding: 12px;
  }
}
</style>
