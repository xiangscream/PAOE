<script setup lang="ts">
import { ref, watch } from 'vue'
import { api, ApiError } from '../api'

const props = defineProps<{ project: string; fallbackIndex?: string; fallbackTeam?: string }>()

const which = ref<'INDEX.md' | 'TEAM.md'>('INDEX.md')
const body = ref('')
const path = ref('')
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  body.value = ''
  path.value = ''
  try {
    const data = await api.document(props.project, which.value)
    body.value = data.body
    path.value = data.path
  } catch (problem) {
    const fallback = which.value === 'INDEX.md' ? props.fallbackIndex : props.fallbackTeam
    if (fallback) {
      body.value = fallback
      path.value = which.value + '（来自 dashboard 读面）'
      error.value = ''
    } else {
      error.value = problem instanceof ApiError ? problem.message : String(problem)
    }
  } finally {
    loading.value = false
  }
}

watch([() => props.project, which], () => void load(), { immediate: true })
</script>

<template>
  <div class="doc">
    <div class="row" style="margin-bottom: 10px">
      <button class="btn" :class="{ primary: which === 'INDEX.md' }" @click="which = 'INDEX.md'">项目 INDEX</button>
      <button class="btn" :class="{ primary: which === 'TEAM.md' }" @click="which = 'TEAM.md'">TEAM 原文</button>
      <span class="spacer"></span>
      <span class="hint">{{ path }}</span>
      <button class="btn ghost" @click="load">刷新</button>
    </div>
    <p v-if="loading" class="hint">读取项目原文…</p>
    <p v-else-if="error" class="card">{{ error }}</p>
    <pre v-else>{{ body || '（该文件为空或尚未建立）' }}</pre>
    <p class="hint">页面只读本地原件；修改仍在项目文件与 Git。</p>
  </div>
</template>
