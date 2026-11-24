import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ChatView from '../src/components/ChatView.vue'

// F87：一次业务按钮 = 一次决定。先 review 读准确 subject，再 confirm 带 decision；
// 不打开第二个确认窗。F88：角色卡只映射后端 group/task，不在前端另存 TODO。

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

const room = () => ({
  ok: true, id: 'task-room', title: 'F87 联调', status: 'open',
  members: [{ home_id: 'human', state: 'participant', presence: 'online', last_read_seq: 0 }],
  owner_id: 'S010', close_policy: 'human_confirm',
  task_context: { goal: 'F87 联调', index_path: 'Works/F87/INDEX.md', project_id: '3002' },
  messages: [],
})

const team = () => ({
  plan: {
    title: 'F87 联调', project: '3002', owner: 'S010', task: 'T-1', version: 1,
    members: ['S010', 'S040'], close_policy: 'human_confirm',
  },
  revision: 3,
  roles: {
    S010: { home: 'S010', revision: 1, approved: false, role: { duty: '后端桥', arrangement: '同批', deliverables: 'bridge.py' } },
    S040: { home: 'S040', revision: 1, approved: false, role: { duty: '前端映射', arrangement: '同批', deliverables: 'TeamPanel.vue' } },
  },
  roles_receipt: null,
  accepted: null,
})

const cards = () => ({
  S010: {
    role: team().roles.S010,
    task: { id: 'T-1', title: '后端桥', state: 'doing', artifact_ref: 'bridge.py' },
    group: {
      name: 'PAOE 0.1', rooms: ['room-a'],
      tasks: [{ id: 'T-1', title: '后端桥', state: 'doing', artifact_ref: 'bridge.py' }],
    },
  },
  S040: {
    role: team().roles.S040,
    task: { id: 'T-2', title: '前端映射', state: 'todo' },
    group: { name: 'PAOE 0.1', rooms: ['room-a'], tasks: [{ id: 'T-2', title: '前端映射', state: 'todo' }] },
  },
})

function mountRoom(overrides: {
  review?: (body: any) => unknown
  confirm?: (body: any) => unknown
} = {}) {
  const reviewBody: any[] = []
  const confirmBody: any[] = []
  const review = vi.fn(async (_path: string, options?: RequestInit) => {
    const body = JSON.parse(String(options?.body))
    reviewBody.push(body)
    return overrides.review ? overrides.review(body) : { ok: true, action: body.action, input: body.input, subject: { revision: body.input.expected_revision ?? body.input.version }, explanation: '审阅原文' }
  })
  const confirm = vi.fn(async (_path: string, options?: RequestInit) => {
    const body = JSON.parse(String(options?.body))
    confirmBody.push(body)
    return overrides.confirm ? overrides.confirm(body) : { ok: true, receipt_id: body.receipt_id, applied: { room_id: 'task-room' } }
  })
  let teamLoads = 0
  const fetch = vi.fn(async (path: string, options?: RequestInit) => {
    if (options?.method === 'POST' && path === '/api/team/review') return { ok: true, json: async () => review(path, options) }
    if (options?.method === 'POST' && path === '/api/team/confirm') return { ok: true, json: async () => confirm(path, options) }
    if (path.startsWith('/api/team-plan')) return { ok: true, json: async () => ({ ok: true, plans: [] }) }
    if (path === '/api/room/task-room/team') { teamLoads++; return { ok: true, json: async () => ({ ok: true, room: 'task-room', team: team(), cards: cards() }) } }
    if (path === '/api/room/task-room') return { ok: true, json: async () => room() }
    if (path.startsWith('/api/cat/rooms')) return { ok: true, json: async () => ({ ok: true, rooms: [{ id: 'task-room', title: 'F87 联调', status: 'open', created_at: '2026-11-24T00:00:00Z' }] }) }
    if (path === '/api/cat/people') return { ok: true, json: async () => ({ ok: true, people: [] }) }
    if (path.startsWith('/api/document')) return { ok: true, json: async () => ({ ok: true, path: '', body: '# INDEX' }) }
    return { ok: true, json: async () => ({ ok: true }) }
  })
  vi.stubGlobal('fetch', fetch)
  vi.stubGlobal('EventSource', vi.fn(function () { return { addEventListener: vi.fn(), close: vi.fn() } }))
  vi.stubGlobal('ResizeObserver', vi.fn(function () { return { observe: vi.fn(), disconnect: vi.fn() } }))
  const wrapper = mount(ChatView, { props: { project: '3002', initialRoom: 'task-room' } })
  const vm = wrapper.vm as unknown as { teamDecide: (arg: any) => Promise<void> }
  return { wrapper, vm, review, confirm, reviewBody, confirmBody, teamLoads: () => teamLoads }
}

describe('F87 one-click UI decision', () => {
  it('reviews the exact displayed input, then confirms once with the reviewed subject', async () => {
    const { wrapper, review, confirm, reviewBody, confirmBody } = mountRoom()
    await flushPromises()
    await wrapper.get('[data-testid="btn-approve-roles"]').trigger('click')
    await flushPromises()

    expect(review).toHaveBeenCalledTimes(1)
    expect(reviewBody[0]).toEqual({ action: 'approve-roles', input: { room: 'task-room', expected_revision: 3 } })
    expect(confirm).toHaveBeenCalledTimes(1)
    const body = confirmBody[0]
    expect(body.action).toBe('approve-roles')
    expect(body.input).toEqual({ room: 'task-room', expected_revision: 3 })
    expect(body.receipt_id).toMatch(/^ha-[0-9a-f]{32}$/)
    expect(body.decision).toEqual({
      choice: 'approve', channel: 'ui', recorded_by: 'human',
      source_ref: 'paoe://ui/room/task-room/approve-roles', quote: '通过',
      subject: { revision: 3 },
    })
    expect(wrapper.get('[data-testid="action-outcome"]').text()).toContain('已生效')
  })

  it('does not confirm when the review has no accurate subject', async () => {
    const { wrapper, confirm } = mountRoom({ review: () => ({ ok: true, explanation: '缺少版本' }) })
    await flushPromises()
    await wrapper.get('[data-testid="btn-approve-roles"]').trigger('click')
    await flushPromises()
    expect(confirm).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="action-outcome"]').text()).toContain('审阅结果缺少准确版本')
  })

  it('shows a version change as conflict and keeps the decision unapplied', async () => {
    const { wrapper } = mountRoom({
      confirm: () => ({ ok: false, error_code: 'local_operation_failed', error: '决定对应的内容已变化，请先对齐受影响的差异' }),
    })
    await flushPromises()
    await wrapper.get('[data-testid="btn-approve-roles"]').trigger('click')
    await flushPromises()
    const outcome = wrapper.get('[data-testid="action-outcome"]')
    expect(outcome.classes()).toContain('outcome-conflict')
    expect(outcome.text()).toContain('内容已变化')
  })

  it('records reject/revise/defer as explicit choices, never as applied', async () => {
    const { wrapper, vm, confirmBody } = mountRoom({
      confirm: body => ({ ok: true, receipt_id: body.receipt_id, state: 'rejected', applied: null, replayed: false }),
    })
    await flushPromises()
    await vm.teamDecide({ action: 'approve-roles', input: { room: 'task-room', expected_revision: 3 }, choice: 'reject' })
    await flushPromises()
    expect(confirmBody[0].decision.choice).toBe('reject')
    expect(wrapper.get('[data-testid="action-outcome"]').text()).toContain('已记录：拒绝')
    expect(wrapper.get('[data-testid="team-stage"]').text()).not.toContain('已验收')
  })
})

describe('F88 grouped TODO mapping', () => {
  it('renders the backend group name, tasks and rooms without a second TODO', async () => {
    const { wrapper } = mountRoom()
    await flushPromises()
    const group = wrapper.get('[data-testid="work-group"]')
    expect(group.text()).toContain('工作：PAOE 0.1')
    expect(group.text()).toContain('进行中 · bridge.py · 后端桥')
    expect(group.text()).toContain('CAT room-a')
    expect(wrapper.text()).not.toContain('新建 TODO')
  })
})
