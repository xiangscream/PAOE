<script setup lang="ts">
import { ref } from 'vue'
import ChatView from '../../front/ui/src/components/ChatView.vue'

const props = defineProps<{
  project: string
  initialRoom: string
  eventUrl: (roomId: string, cursor: number) => string
  streamFactory?: (url: string) => any
}>()
const emit = defineEmits<{
  (event: 'new-discussion'): void
  (event: 'board'): void
  (event: 'room-selected', id: string): void
}>()
const chatRef = ref<InstanceType<typeof ChatView> | null>(null)

function selectRoom(id: string) {
  return chatRef.value?.selectRoom(id)
}

defineExpose({ selectRoom })
</script>

<template>
  <div class="paos-cat-panel">
    <ChatView
      ref="chatRef"
      :project="props.project"
      :initial-room="props.initialRoom"
      :event-url="props.eventUrl"
      :stream-factory="props.streamFactory"
      embedded
      @new-discussion="emit('new-discussion')"
      @board="emit('board')"
      @room-selected="emit('room-selected', $event)"
    />
  </div>
</template>

<style scoped>
.paos-cat-panel {height:100%;min-height:0;overflow:hidden}
</style>
