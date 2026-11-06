import type { CollabMode, CollabResult, CollabState } from '../types'

export interface Reference {
  title: string
  path: string
  kind: string
  id?: string
}

export interface CollaborationDraft {
  provider: string
  receiver: string
  topic: string
  note: string
  mode: CollabMode
  remind: boolean
  reference?: Reference | null
}

export function createMessageId(): string {
  return 'ui-' + (globalThis.crypto?.randomUUID?.() ?? Math.random().toString(16).slice(2))
}

export function validateDraft(draft: CollaborationDraft): string {
  if (!draft.receiver) return '请选择接收方。'
  if (!draft.topic.trim()) return '请填写本次协作主题。'
  if (draft.mode === 'chat' && (!draft.provider || draft.provider === draft.receiver)) {
    return 'Chat 需要提供方和接收方两位不同同事。'
  }
  return ''
}

export function buildBody(draft: CollaborationDraft): string {
  const lines = [
    `主题：${draft.topic.trim()}`,
    `提供方：${draft.provider || 'Human'}`,
    `接收方：${draft.receiver}`,
    '',
    draft.note.trim() || '（无补充说明）',
  ]
  if (draft.reference) {
    lines.push('', `参考：${draft.reference.title}`, draft.reference.path)
  }
  return lines.join('\n')
}

export function membersFor(draft: CollaborationDraft): string[] {
  if (draft.mode === 'chat') return [draft.provider, draft.receiver]
  // Agent -> Agent Mail keeps both sides so the provider also receives the topic request.
  // A single reference Mail from Human only goes to the receiver.
  return draft.provider && draft.provider !== 'human' && draft.provider !== draft.receiver
    ? [draft.provider, draft.receiver]
    : [draft.receiver]
}

export function payloadFor(draft: CollaborationDraft, project: string, messageId = createMessageId()) {
  return {
    project,
    mode: draft.mode,
    members: membersFor(draft),
    topic: draft.topic.trim(),
    body: buildBody(draft),
    message_id: messageId,
    remind: draft.remind,
  }
}

function inferredState(result: CollabResult): CollabState {
  if (result.state) return result.state
  if (result.ok === true && result.message_id) return 'saved'
  if (result.room_id && !result.message_id) return 'partial'
  const status = result.status || 0
  if ([400, 404, 409, 422].includes(status)) return 'failed'
  return 'unknown'
}

export function outcomeOf(result: CollabResult | null, thrown?: unknown): { state: CollabState; text: string } {
  if (!result) {
    const detail = thrown ? String((thrown as Error)?.message || thrown) : '本地服务没有回执'
    return { state: 'unknown', text: `结果未确认：${detail}。保留本次请求，先核对，不自动重发。` }
  }
  const state = inferredState(result)
  if (state === 'saved') {
    const notify =
      result.notification === 'queued'
        ? '提醒已排队'
        : result.notification === 'accepted'
          ? '提醒已受理'
          : result.notification === 'not_requested'
            ? '未请求提醒'
            : '提醒结果未知'
    return { state: 'saved', text: `已保存 · ${notify}。保存不代表对方已读或接手。` }
  }
  if (state === 'partial') {
    return { state: 'partial', text: '部分完成：已有房间或已入席，尚未完成全部发送。保留原请求，按已知房间继续核对。' }
  }
  if (state === 'failed') {
    return { state: 'failed', text: '未提交：' + (result.error || '请求被拒绝') + '。可修正后重新提交。' }
  }
  return { state: 'unknown', text: '结果未确认：请核对原 Mail／房间，保留输入，不自动重发。' }
}

export function canResubmit(state: CollabState | ''): boolean {
  return state === 'failed' || state === ''
}
