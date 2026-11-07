<script setup lang="ts">
import { computed, ref } from 'vue'
import { renderMarkdown } from '../lib/markdown'

const props = defineProps<{ body: string; path?: string }>()
const emit = defineEmits<{ (e: 'navigate', href: string): void; (e: 'copy', path: string): void }>()
const raw = ref(false)
const html = computed(() => renderMarkdown(props.body || ''))

function onClick(event: MouseEvent) {
  const anchor = (event.target as HTMLElement | null)?.closest('a')
  if (!anchor) return
  const href = anchor.getAttribute('href') || ''
  if (!href || /^(https?:|mailto:|#)/i.test(href)) return
  event.preventDefault()
  emit('navigate', href)
}
</script>

<template>
  <div class="doc-view">
    <div class="doc-toolbar">
      <span class="doc-path" :title="props.path">{{ props.path }}</span>
      <button v-if="props.path" class="btn ghost" type="button" @click="emit('copy', props.path!)">复制路径</button>
      <button class="btn ghost" type="button" @click="raw = !raw">{{ raw ? '阅读视图' : '原文' }}</button>
    </div>
    <pre v-if="raw" class="doc-raw">{{ props.body }}</pre>
    <article v-else class="markdown-body" v-html="html" @click="onClick"></article>
  </div>
</template>

<style scoped>
.doc-view {
  display: grid;
  grid-template-columns: minmax(0,1fr);
  gap: 8px;
  min-width: 0;
}

.doc-toolbar {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  color: var(--muted);
  font-size: 12px;
}

.doc-path {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.doc-raw {
  margin: 0;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface);
  font: 12px/1.65 ui-monospace, Consolas, monospace;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 60vh;
  overflow: auto;
}

.markdown-body {
  min-width: 0;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 16px 18px;
  color: var(--ink);
  font-size: 14px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  line-height: 1.35;
  margin: 18px 0 8px;
}

.markdown-body :deep(h1) { font-size: 20px; }
.markdown-body :deep(h2) { font-size: 17px; }
.markdown-body :deep(h3) { font-size: 15px; }

.markdown-body :deep(p) { margin: 8px 0; }

.markdown-body :deep(ul),
.markdown-body :deep(ol) { padding-left: 22px; margin: 8px 0; }
.markdown-body :deep(ul) {list-style-type:disc}
.markdown-body :deep(ol) {list-style-type:decimal}

.markdown-body :deep(li) { margin: 3px 0; }

.markdown-body :deep(a) {
  color: var(--accent);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.markdown-body :deep(code) {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 1px 4px;
  font: 12px/1.5 ui-monospace, Consolas, monospace;
}

.markdown-body :deep(pre) {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px 12px;
  overflow: auto;
}

.markdown-body :deep(pre code) {
  border: 0;
  background: transparent;
  padding: 0;
}

.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: 13px;
  display: block;
  overflow-x: auto;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--line);
  padding: 6px 8px;
  text-align: left;
  vertical-align: top;
}

.markdown-body :deep(th) { background: var(--paper); }

.markdown-body :deep(blockquote) {
  margin: 10px 0;
  padding: 6px 12px;
  border-left: 3px solid var(--line);
  color: var(--muted);
}

.markdown-body :deep(hr) {
  border: 0;
  border-top: 1px solid var(--line);
  margin: 14px 0;
}
</style>
