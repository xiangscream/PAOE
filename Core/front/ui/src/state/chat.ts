import type { ChatMessage, CollabResult } from '../types'

export function mergeMessages(previous: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  const byId = new Map(previous.map(message => [message.id, message]))
  for (const message of incoming) byId.set(message.id, message)
  return [...byId.values()].sort((a, b) => a.seq - b.seq)
}

export function readPage(timeline: { messages: ChatMessage[]; cursor: number }, messages: ChatMessage[]) {
  return {
    messages: mergeMessages(timeline.messages, messages),
    cursor: Math.max(timeline.cursor, ...messages.map(message => message.seq), 0),
  }
}

export function acceptMessage(timeline: { messages: ChatMessage[]; cursor: number }, message: ChatMessage) {
  return { messages: mergeMessages(timeline.messages, [message]), cursor: timeline.cursor }
}

export function sendOutcome(value: CollabResult | null): { state: 'saved' | 'failed' | 'unknown'; text: string } {
  if (value?.ok && value.state !== 'failed' && value.message_id) {
    const dispatch = value.notification
    const text =
      dispatch === 'queued'
        ? '已保存 · 提醒已排队'
        : dispatch === 'not_requested'
          ? '已保存 · 未请求提醒'
          : '已保存 · 提醒结果以原回执为准'
    return { state: 'saved', text }
  }
  const definite =
    value?.state === 'failed' ||
    value?.status === 400 ||
    value?.status === 404 ||
    value?.status === 409 ||
    value?.status === 422
  return definite
    ? { state: 'failed', text: '未发送：' + (value?.error || '请求被拒绝') }
    : { state: 'unknown', text: '发送结果尚未确认。请核对原消息，保留输入，暂不重发。' }
}

export function draftKey(project: string, roomId: string) {
  return `poe.draft.${project}.${roomId}`
}

export function saveDraft(project: string, roomId: string, value: { body: string; reply: string }) {
  try {
    localStorage.setItem(draftKey(project, roomId), JSON.stringify(value))
  } catch {
    /* storage may be unavailable */
  }
}

export function loadDraft(project: string, roomId: string): { body: string; reply: string } {
  try {
    const raw = localStorage.getItem(draftKey(project, roomId))
    if (!raw) return { body: '', reply: '' }
    const value = JSON.parse(raw)
    return { body: String(value.body || ''), reply: String(value.reply || '') }
  } catch {
    return { body: '', reply: '' }
  }
}
