import { describe, expect, it } from 'vitest'
import { defaultNodes, mergeLayout } from '../src/state/layout'
import { buildBody, canResubmit, membersFor, outcomeOf, payloadFor, validateDraft } from '../src/state/collab'
import { canStartCollaboration, displayName, isPaused, statusLabel } from '../src/state/team'
import type { AgentSummary, BoardLayout } from '../src/types'

const agent = (id: string, extra: Partial<AgentSummary> = {}): AgentSummary => ({ id, ok: true, ...extra })

describe('layout', () => {
  it('gives every registered member a default slot without overlap', () => {
    const nodes = defaultNodes([agent('a'), agent('b'), agent('c')])
    const values = Object.values(nodes)
    expect(values).toHaveLength(3)
    expect(new Set(values.map(v => `${v.x},${v.y}`)).size).toBe(3)
  })

  it('keeps saved positions and viewport while adding new members', () => {
    const saved: Partial<BoardLayout> = {
      nodes: { a: { x: 120, y: 60 } },
      viewport: { x: 10, y: 20, zoom: 1.2 },
    }
    const layout = mergeLayout([agent('a'), agent('b')], saved)
    expect(layout.nodes.a).toEqual({ x: 120, y: 60 })
    expect(layout.nodes.b).toBeTruthy()
    expect(layout.viewport).toEqual(saved.viewport)
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

  it('keeps every selected participant without duplicating the two named roles',()=>{
    const group={...draft,participants:['A','B','C']}
    expect(membersFor(group)).toEqual(['A','B','C'])
    expect(membersFor({...group,mode:'mail'})).toEqual(['A','B','C'])
    expect(buildBody(group)).toContain('其他参与者：C')
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
