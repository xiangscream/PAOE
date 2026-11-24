import { describe, expect, it } from 'vitest'
import {
  HUMAN_ACTIONS, planMembers, planSummary, roleCardState, roleLine, teamStage,
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
    // One still draft → not released
    expect(teamStage({ roles: {
      S040: { home: 'S040', role: { duty: '前端' }, approved: true, revision: 2 },
      S010: { home: 'S010', role: { duty: '后端' }, approved: false, revision: 1 },
    } })).toMatchObject({ label: '已建房·角色收集中', tone: 'draft' })
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
    expect(planSummary({ owner: 'S010', close_policy: 'owner' })).toBe('负责人 S010 · 负责人可关')
  })
  it('filters non-string members', () => {
    expect(planMembers({ members: ['S010', 42, null, 'S040'] })).toEqual(['S010', 'S040'])
    expect(planMembers(null)).toEqual([])
  })
})

describe('HUMAN_ACTIONS (四步口径)', () => {
  it('labels open-plan as first release and approve-roles as second', () => {
    expect(HUMAN_ACTIONS['open-plan'].hint).toContain('第一次放行')
    expect(HUMAN_ACTIONS['approve-roles'].hint).toContain('第二次放行')
    expect(HUMAN_ACTIONS['open-plan'].label).toBe('通过计划并建房')
    expect(HUMAN_ACTIONS['approve-roles'].label).toBe('放行角色卡')
  })
  it('labels task-accept as the Human reserved final acceptance', () => {
    expect(HUMAN_ACTIONS['task-accept'].hint).toContain('Human 保留')
    expect(HUMAN_ACTIONS['save-role'].hint).toContain('不触发放行')
  })
  it('orders the four actions: save, open-plan, approve-roles, task-accept', () => {
    expect(HUMAN_ACTIONS['save-role'].order).toBeLessThan(HUMAN_ACTIONS['open-plan'].order)
    expect(HUMAN_ACTIONS['open-plan'].order).toBeLessThan(HUMAN_ACTIONS['approve-roles'].order)
    expect(HUMAN_ACTIONS['approve-roles'].order).toBeLessThan(HUMAN_ACTIONS['task-accept'].order)
  })
})

describe('roleLine', () => {
  it('joins duty, arrangement and deliverables with ·', () => {
    expect(roleLine({ duty: '前端', arrangement: 'Vue', deliverables: 'index.html' })).toBe('前端 · Vue · index.html')
    expect(roleLine(null)).toBe('')
    expect(roleLine({})).toBe('')
  })
})
