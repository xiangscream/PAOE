<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import type { AgentSummary } from '../types'
import { actionText, displayName, displayNumber, displayRole, isPaused, statusLabel } from '../state/team'

const props = defineProps<{ data: { agent: AgentSummary; openLibrary?: (id: string) => void } }>()
</script>

<template>
  <div
    class="person-node"
    :class="{ paused: isPaused(props.data.agent), unreadable: props.data.agent.ok === false }"
  >
    <Handle type="target" :position="Position.Left" />
    <Handle type="source" :position="Position.Right" />
    <button
      class="more"
      type="button"
      :aria-label="'为 ' + displayName(props.data.agent) + ' 选择 Libraries 参考'"
      title="选择 Libraries 参考"
      @click.stop="props.data.openLibrary?.(props.data.agent.id)"
    >…</button>
    <div class="who">
      <strong :title="displayName(props.data.agent)">{{ displayName(props.data.agent) }}</strong>
      <span class="number">{{ displayNumber(props.data.agent) }}</span>
    </div>
    <div class="role" :title="displayRole(props.data.agent)">{{ displayRole(props.data.agent) }}</div>
    <div class="action" :title="actionText(props.data.agent)">{{ actionText(props.data.agent) }}</div>
    <div class="foot">
      <span class="status-dot" :class="{ warn: isPaused(props.data.agent), off: props.data.agent.ok === false }"></span>
      <span>{{ statusLabel(props.data.agent) }}</span>
      <span v-if="props.data.agent.pending_notices">· {{ props.data.agent.pending_notices }} 待处理</span>
      <span v-if="props.data.agent.tasks?.doing">· {{ props.data.agent.tasks?.doing }} 进行中</span>
    </div>
  </div>
</template>
