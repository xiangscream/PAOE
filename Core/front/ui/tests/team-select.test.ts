import { describe, expect, it } from 'vitest'
import {
  HUMAN_ACTIONS, actionOutcome, cardTaskLine, confirmInput,
  planMembers, planSummary, roleCardState, roleLine, teamStage,
} from '../../team-select.mjs'

describe('roleCardState', () => {
  it('marks empty entries as 未提交 with a hint', () => {
    expect(roleCardState(null)).toMatchObject({ kind: 'empty', label: '未提交' })
    expect(roleCardState({})).toMatchObject({ kind: 'empty' })
    expect(roleCardState({ role: null })).toMatchObject({ kind: 'empty' })
  })
  it('separates drafts (approved=false) from released (approved=true) by revision', () => {
    expect(roleCardState({ role: { duty: '前端' }, approved: false, revision: 2 }))
      .toMatchObject({ kind: 'draft', label: '草案', revision: 2 })
    expect(roleCardState({ role: { duty: '前端' }, approved: true, revision: 3 }))
      .toMatchObject({ kind: 'approved', label: '角色已放行', revision: 3 })
  })
  it('treats missing approved as draft, never guesses approved', () => {
    expect(roleCardState({ role: { duty: 'x' }, revision: 1 })).toMatchObject({ kind: 'draft', label: '草案' })
  })
})

describe('teamStage (两次放行：open-plan 第一次 → approve-roles 第二次)', () => {
  it('starts at 已建房·角色收集中 when no roles are submitted', () => {
    expect(teamStage({ roles: {} })).toMatchObject({ label: '已建房·角色收集中', tone: 'draft' })
  })
  it('shows same stage when any draft is pending Human second release', () => {
    expect(teamStage({ roles: { S040: { role: { duty: 'x' }, approved: false, revision: 1 } } }))
      .toMatchObject({ label: '已建房·角色收集中', tone: 'draft' })
  })
  it('shows 角色已放行 only when every submitted card is approved', () => {
    expect(teamStage({ roles: {
      S040: { home: 'S040', role: { duty: '前端' }, approved: true, revision: 2 },
      S010: { home: 'S010', role: { duty: '后端' }, approved: true, revision: 2 },
    } })).toMatchObject({ label: '角色已放行', tone: 'released' })
  })
  it('accepted or owner_acceptance overrides everything', () => {
    expect(teamStage({ accepted: true, roles: {} })).toMatchObject({ label: '已验收·房可关闭', tone: 'accepted' })
    expect(teamStage({ owner_acceptance: 'oa-abc', roles: {} })).toMatchObject({ label: '已验收·房可关闭', tone: 'accepted' })
  })
})

describe('planSummary and planMembers', () => {
  it('summarizes project, owner, version, close policy and member count', () => {
    const plan = { project: '3002', owner: 'S010', version: 3, close_policy: 'human_confirm', members: ['S010', 'S040', 'S063'] }
    expect(planSummary(plan)).toBe('项目 3002 · 负责人 S010 · v3 · 关房需 Human 确认 · 3 名成员')
  })
  it('filters non-string members', () => {
    expect(planMembers({ members: ['S010', 42, null, 'S040'] })).toEqual(['S010', 'S040'])
  })
})

describe('HUMAN_ACTIONS (四步口径，accept-goal 非 task-accept)', () => {
  it('labels open-plan as first release and approve-roles as second', () => {
    expect(HUMAN_ACTIONS['open-plan'].hint).toContain('第一次放行')
    expect(HUMAN_ACTIONS['approve-roles'].hint).toContain('第二次放行')
  })
  it('uses accept-goal (not task-accept) for Human reserved final acceptance', () => {
    expect(HUMAN_ACTIONS['accept-goal']).toBeDefined()
    expect((HUMAN_ACTIONS as Record<string, unknown>)['task-accept']).toBeUndefined()
    expect(HUMAN_ACTIONS['accept-goal'].hint).toContain('Human 保留')
  })
  it('orders the four actions: save, open-plan, approve-roles, accept-goal', () => {
    expect(HUMAN_ACTIONS['save-role'].order).toBeLessThan(HUMAN_ACTIONS['open-plan'].order)
    expect(HUMAN_ACTIONS['open-plan'].order).toBeLessThan(HUMAN_ACTIONS['approve-roles'].order)
    expect(HUMAN_ACTIONS['approve-roles'].order).toBeLessThan(HUMAN_ACTIONS['accept-goal'].order)
  })
})

describe('confirmInput (四种正式合同)', () => {
  it('assembles open-plan {owner,task,version}', () => {
    expect(confirmInput('open-plan', { owner: 'S010', task: 'T1', version: 3 }))
      .toEqual({ owner: 'S010', task: 'T1', version: 3 })
  })
  it('assembles approve-roles {room,expected_revision}', () => {
    expect(confirmInput('approve-roles', { room: 'r1', expected_revision: 2 }))
      .toEqual({ room: 'r1', expected_revision: 2 })
  })
  it('assembles save-role {room,home,expected_revision,role}', () => {
    expect(confirmInput('save-role', { room: 'r1', home: 'S040', expected_revision: 1, role: { duty: '前端', arrangement: 'Vue', deliverables: 'ui' } }))
      .toEqual({ room: 'r1', home: 'S040', expected_revision: 1, role: { duty: '前端', arrangement: 'Vue', deliverables: 'ui' } })
  })
  it('assembles accept-goal {room,task,artifact,basis,remaining,read_to}', () => {
    expect(confirmInput('accept-goal', { room: 'r1', task: 'T1', artifact: 'a.md', basis: 'b.md', remaining: 'none', read_to: 5 }))
      .toEqual({ room: 'r1', task: 'T1', artifact: 'a.md', basis: 'b.md', remaining: 'none', read_to: 5 })
  })
  it('returns null for unknown actions', () => {
    expect(confirmInput('unknown-action', {})).toBeNull()
  })
})

describe('actionOutcome (applied / cancelled / conflict / failed)', () => {
  it('marks applied on ok+applied', () => {
    expect(actionOutcome({ ok: true, applied: true })).toMatchObject({ kind: 'applied', text: '已生效' })
    expect(actionOutcome({ ok: true, state: 'applied' })).toMatchObject({ kind: 'applied' })
  })
  it('marks cancelled on cancelled flag', () => {
    expect(actionOutcome({ ok: false, cancelled: true })).toMatchObject({ kind: 'cancelled', text: 'Human 取消了操作' })
    expect(actionOutcome({ state: 'cancelled' })).toMatchObject({ kind: 'cancelled' })
  })
  it('marks conflict on revision/conflit/stale error codes', () => {
    expect(actionOutcome({ ok: false, error_code: 'revision_mismatch' }))
      .toMatchObject({ kind: 'conflict', text: expect.stringContaining('版本冲突') })
    expect(actionOutcome({ ok: false, error_code: 'stale_revision' }))
      .toMatchObject({ kind: 'conflict' })
  })
  it('marks failed on other errors and unknown results', () => {
    expect(actionOutcome({ ok: false, error: '拒绝' })).toMatchObject({ kind: 'failed', text: '拒绝' })
    expect(actionOutcome(null)).toMatchObject({ kind: 'failed' })
    expect(actionOutcome({ ok: true })).toMatchObject({ kind: 'failed', text: '结果未确认' })
  })
})

describe('cardTaskLine', () => {
  it('shows task state and artifact', () => {
    expect(cardTaskLine({ task: { state: 'doing', artifact_ref: 'result.md' } })).toBe('进行中 · result.md')
    expect(cardTaskLine({ task: { state: 'done', title: '前端交付' } })).toBe('已完成 · 前端交付')
  })
  it('returns empty for null or missing task', () => {
    expect(cardTaskLine(null)).toBe('')
    expect(cardTaskLine({})).toBe('')
    expect(cardTaskLine({ task: null })).toBe('')
  })
})
