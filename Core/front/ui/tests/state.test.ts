import { describe, expect, it } from 'vitest'
import { defaultNodes, mergeLayout } from '../src/state/layout'
import { buildBody, canResubmit, membersFor, outcomeOf, payloadFor, validateDraft } from '../src/state/collab'
import { acceptMessage, loadDraft, mergeMessages, readPage, saveDraft, sendOutcome } from '../src/state/chat'
import { canStartCollaboration, displayName, isPaused, statusLabel } from '../src/state/team'
import type { AgentSummary, BoardLayout, ChatMessage } from '../src/types'

const agent = (id: string, extra: Partial<AgentSummary> = {}): AgentSummary => ({ id, ok: true, ...extra })
const message = (id: string, seq: number): ChatMessage => ({
  id, seq, sender_id: 'human', body: id, created_at: '2026-11-07T00:00:00Z',
})

describe('layout', () => {
  it('gives every registered member a default slot without overlap', () => {
    const nodes = defaultNodes([agent('a'), agent('b'), agent('c')])
    const values = Object.values(nodes)
    expect(values).toHaveLength(3)
    expect(new Set(values.map(v => `${v.x},${v.y}`)).size).toBe(3)
  })

  it('keeps saved positions, adds new members and clamps the viewport', () => {
    const saved: Partial<BoardLayout> = {
      nodes: { a: { x: 120, y: 60 } },
      viewport: { x: 10, y: 20, zoom: 99 },
    }
    const layout = mergeLayout([agent('a'), agent('b')], saved)
    expect(layout.nodes.a).toEqual({ x: 120, y: 60 })
    expect(layout.nodes.b).toBeTruthy()
    expect(layout.viewport.zoom).toBeLessThanOrEqual(2.5)
  })

  it('ignores non-finite coordinates from a broken layout file', () => {
    const layout = mergeLayout([agent('a')], { nodes: { a: { x: Number.NaN, y: 4 } }, viewport: { x: 0, y: 0, zoom: 1 } })
    expect(Number.isFinite(layout.nodes.a.x)).toBe(true)
    expect(layout.nodes.a.y).toBe(4)
  })
})

describe('collaboration', () => {
  const draft = {
    provider: 'A', receiver: 'B', topic: '补充资料', note: '请接一下', mode: 'chat' as const,
    remind: true, reference: { title: 'Handoff', path: 'workflow/handoff.md', kind: 'skill' },
  }

  it('requires a receiver and topic, and two people for chat', () => {
    expect(validateDraft({ ...draft, receiver: '' })).not.toBe('')
    expect(validateDraft({ ...draft, topic: ' ' })).not.toBe('')
    expect(validateDraft({ ...draft, receiver: 'A' })).not.toBe('')
    expect(validateDraft(draft)).toBe('')
    expect(validateDraft({ ...draft, provider: 'human' })).not.toBe('')
  })

  it('allows a single receiver for a reference mail', () => {
    expect(validateDraft({ ...draft, mode: 'mail', provider: 'human' })).toBe('')
    expect(membersFor({ ...draft, mode: 'mail' })).toEqual(['A', 'B'])
    expect(membersFor({ ...draft, mode: 'mail', provider: 'human' })).toEqual(['B'])
  })

  it('shows provider, receiver, topic and the reference path before submit', () => {
    const body = buildBody(draft)
    expect(body).toContain('提供方：A')
    expect(body).toContain('接收方：B')
    expect(body).toContain('主题：补充资料')
    expect(body).toContain('workflow/handoff.md')
  })

  it('keeps one stable message id and never auto-resubmits unknown results', () => {
    const first = payloadFor(draft, '3002', 'ui-fixed')
    const second = payloadFor(draft, '3002', 'ui-fixed')
    expect(first.message_id).toBe(second.message_id)
    expect(canResubmit('unknown')).toBe(false)
    expect(canResubmit('partial')).toBe(false)
    expect(canResubmit('failed')).toBe(true)
    expect(outcomeOf({ state: 'unknown' }).state).toBe('unknown')
    expect(outcomeOf({ state: 'saved', notification: 'not_requested' }).text).toContain('未请求提醒')
    expect(outcomeOf({ state: 'saved', notification: 'queued' }).text).toContain('已保存')
    expect(outcomeOf({ state: 'saved', notification: 'partial' }).text).toContain('部分提醒未受理')
    expect(payloadFor(draft, '3002', 'ui-1', 'room-9').room_id).toBe('room-9')
  })
})

describe('chat state', () => {
  it('sorts merged messages and advances the cursor only from reads', () => {
    let timeline = { messages: [message('a', 1)], cursor: 1 }
    timeline = acceptMessage(timeline, message('c', 3))
    expect(timeline.cursor).toBe(1)
    timeline = readPage(timeline, [message('b', 2), message('c', 3)])
    expect(timeline.messages.map(m => m.id)).toEqual(['a', 'b', 'c'])
    expect(timeline.cursor).toBe(3)
  })

  it('treats missing or non-definite results as unknown', () => {
    expect(sendOutcome(null).state).toBe('unknown')
    expect(sendOutcome({ ok: false, status: 500 }).state).toBe('unknown')
    expect(sendOutcome({ ok: false, status: 409 }).state).toBe('failed')
    expect(sendOutcome({ ok: true, state: 'saved', message_id: 'm' }).state).toBe('saved')
  })

  it('persists drafts per project and room', () => {
    saveDraft('3002', 'room-1', { body: '未发送', reply: 'm1' })
    expect(loadDraft('3002', 'room-1')).toEqual({ body: '未发送', reply: 'm1' })
    expect(loadDraft('3002', 'room-2')).toEqual({ body: '', reply: '' })
  })
})

describe('team view', () => {
  it('marks paused or unregistered members without inventing presence', () => {
    const paused = agent('s027', { member_status: 'paused', can_contact: false })
    expect(isPaused(paused)).toBe(true)
    expect(canStartCollaboration(paused)).toBe(false)
    expect(statusLabel(paused)).toBe('暂停')
    expect(statusLabel(agent('x', { registered: false }))).toBe('尚未接入')
    expect(displayName(agent('x', { name: 'S052 · 学习' }))).toContain('S052')
  })
})
