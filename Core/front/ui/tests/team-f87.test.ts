import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ChatView from '../src/components/ChatView.vue'

// F87：一次业务按钮 = 一次决定。输入准备好时先 review 并在界面展示，
// 按钮只提交与已显示快照相同的 subject；点击时不再取新 review。
// F88：角色卡只映射后端 group/task，不在前端另存 TODO。

const mounted: any[] = []
afterEach(() => {
  mounted.splice(0).forEach(wrapper => wrapper.unmount())
  vi.unstubAllGlobals()
  localStorage.clear()
  history.replaceState(null, '', '/')
})

const room = () => ({
  ok: true, id: 'task-room', title: 'F87 联调', status: 'open',
  members: [{ home_id: 'human', state: 'participant', presence: 'online', last_read_seq: 0 }],
  owner_id: 'S010', close_policy: 'human_confirm',
  task_context: { goal: 'F87 联调', index_path: 'Works/F87/INDEX.md', project_id: '3002' },
  messages: [],
})

const team = (revision: number, approved = false) => ({
  plan: {
    title: 'F87 联调', project: '3002', owner: 'S010', task: 'T-1', version: 1,
    members: ['S010', 'S040'], close_policy: 'human_confirm',
  },
  revision,
  roles: {
    S010: { home: 'S010', revision: 1, approved, role: { duty: '后端桥', arrangement: '同批', deliverables: 'bridge.py' } },
    S040: { home: 'S040', revision: 1, approved, role: { duty: '前端映射', arrangement: '同批', deliverables: 'TeamPanel.vue' } },
  },
  roles_receipt: null,
  accepted: null,
})

const cards = () => ({
  S010: {
    role: team(3).roles.S010,
    task: { id: 'T-1', title: '后端桥', state: 'doing', artifact_ref: 'bridge.py' },
    group: {
      name: 'PAOE 0.1', rooms: ['room-a'],
      tasks: [{ id: 'T-1', title: '后端桥', state: 'doing', artifact_ref: 'bridge.py' }],
    },
  },
  S040: {
    role: team(3).roles.S040,
    task: { id: 'T-2', title: '前端映射', state: 'todo' },
    group: { name: 'PAOE 0.1', rooms: ['room-a'], tasks: [{ id: 'T-2', title: '前端映射', state: 'todo' }] },
  },
})

function mountRoom(overrides: {
  review?: (body: any) => unknown
  confirm?: (body: any) => unknown
  approved?: boolean
  noRoom?: boolean
  plans?: any[]
  rolesReceipt?: string | null
} = {}) {
  let teamRevision = 3
  let serverSubject = { revision: 3 }
  let deferReview = false
  let resolveDeferred: ((value: unknown) => void) | null = null
  const reviewBody: any[] = []
  const confirmBody: any[] = []
  const review = vi.fn(async (_path: string, options?: RequestInit) => {
    const body = JSON.parse(String(options?.body))
    reviewBody.push(body)
    if (deferReview) return new Promise(resolve => { resolveDeferred = resolve })
    if (overrides.review) return overrides.review(body)
    const subject = body.action === 'accept-goal'
      ? { room: body.input.room, task: body.input.task }
      : body.action === 'save-role'
        ? { room: body.input.room, home: body.input.home, revision: body.input.expected_revision }
        : { revision: body.input.expected_revision ?? body.input.version }
    return { ok: true, action: body.action, input: body.input, subject, explanation: '审阅原文：' + body.action }
  })
  const confirm = vi.fn(async (_path: string, options?: RequestInit) => {
    const body = JSON.parse(String(options?.body))
    confirmBody.push(body)
    if (overrides.confirm) return overrides.confirm(body)
    if (JSON.stringify(body.decision.subject) !== JSON.stringify(serverSubject)) {
      return { ok: false, error_code: 'local_operation_failed', error: '决定对应的内容已变化，请先对齐受影响的差异' }
    }
    return { ok: true, receipt_id: body.receipt_id, applied: { room_id: 'task-room' } }
  })
  const fetch = vi.fn(async (path: string, options?: RequestInit) => {
    if (options?.method === 'POST' && path === '/api/team/review') return { ok: true, json: async () => review(path, options) }
    if (options?.method === 'POST' && path === '/api/team/confirm') return { ok: true, json: async () => confirm(path, options) }
    if (path.startsWith('/api/team-plan')) return { ok: true, json: async () => ({ ok: true, plans: overrides.plans || [] }) }
    if (path === '/api/room/task-room/team') return { ok: true, json: async () => ({ ok: true, room: 'task-room', team: { ...team(teamRevision, overrides.approved === true), roles_receipt: overrides.rolesReceipt ?? null }, cards: cards() }) }
    if (path === '/api/room/task-room') return { ok: true, json: async () => room() }
    if (path.startsWith('/api/cat/rooms')) return { ok: true, json: async () => ({ ok: true, rooms: overrides.noRoom ? [] : [{ id: 'task-room', title: 'F87 联调', status: 'open', created_at: '2026-11-24T00:00:00Z' }] }) }
    if (path === '/api/cat/people') return { ok: true, json: async () => ({ ok: true, people: [] }) }
    if (path.startsWith('/api/document')) return { ok: true, json: async () => ({ ok: true, path: '', body: '# INDEX' }) }
    return { ok: true, json: async () => ({ ok: true }) }
  })
  vi.stubGlobal('fetch', fetch)
  vi.stubGlobal('EventSource', vi.fn(function () { return { addEventListener: vi.fn(), close: vi.fn() } }))
  vi.stubGlobal('ResizeObserver', vi.fn(function () { return { observe: vi.fn(), disconnect: vi.fn() } }))
  const wrapper = mount(ChatView, { props: { project: '3002', initialRoom: overrides.noRoom ? '' : 'task-room' } })
  mounted.push(wrapper)
  const vm = wrapper.vm as unknown as {
    teamDecide: (arg: any) => Promise<void>
    loadTeam: (state: any) => Promise<void>
    roomStates: Record<string, any>
  }
  return {
    wrapper, vm, review, confirm, reviewBody, confirmBody,
    setRevision(value: number) { teamRevision = value },
    setServerSubject(value: any) { serverSubject = value },
    setDefer(value: boolean) { deferReview = value },
    releaseReview(value: unknown) { resolveDeferred?.(value); resolveDeferred = null },
  }
}

async function settle() { await flushPromises(); await flushPromises() }

describe('F87 one-click UI decision', () => {
  it('shows the reviewed snapshot and submits exactly it without re-reading at click', async () => {
    const { wrapper, review, confirm, reviewBody, confirmBody } = mountRoom({
      confirm: body => {
        expect(reviewBody).toHaveLength(1)           // 提交时仍是此前已展示的那一份
        return { ok: true, receipt_id: body.receipt_id, applied: { room_id: 'task-room' } }
      },
    })
    await settle()
    const box = wrapper.get('[data-testid="review-approve-roles"]')
    expect(box.text()).toContain('审阅原文：approve-roles')
    expect(box.text()).toContain('本次审阅版本 r3')

    await wrapper.get('[data-testid="btn-approve-roles"]').trigger('click')
    await settle()

    expect(review.mock.calls.length).toBeGreaterThanOrEqual(1)
    expect(reviewBody[0]).toEqual({ action: 'approve-roles', input: { room: 'task-room', expected_revision: 3 } })
    expect(confirm).toHaveBeenCalledTimes(1)
    const body = confirmBody[0]
    expect(body.input).toEqual({ room: 'task-room', expected_revision: 3 })
    expect(body.receipt_id).toMatch(/^ha-[0-9a-f]{32}$/)
    expect(body.decision).toEqual({
      choice: 'approve', channel: 'ui', recorded_by: 'human',
      source_ref: 'paoe://ui/room/task-room/approve-roles', quote: '通过',
      subject: { revision: 3 },
    })
    expect(wrapper.get('[data-testid="action-outcome"]').text()).toContain('已生效')
  })

  it('keeps the displayed subject when the source changes before the click', async () => {
    const { wrapper, review, confirmBody, setServerSubject } = mountRoom()
    await settle()
    setServerSubject({ revision: 4 })                 // 页面仍显示 r3，后台已到 r4
    await wrapper.get('[data-testid="btn-approve-roles"]').trigger('click')
    await settle()

    expect(review).toHaveBeenCalledTimes(1)           // 点击不重新取 subject
    expect(confirmBody[0].decision.subject).toEqual({ revision: 3 })
    const outcome = wrapper.get('[data-testid="action-outcome"]')
    expect(outcome.classes()).toContain('outcome-conflict')
    expect(outcome.text()).toContain('内容已变化')
  })

  it('keeps the same receipt id and subject for an unknown network result', async () => {
    let first = true
    const { wrapper, review, confirm, reviewBody, confirmBody } = mountRoom({
      confirm: body => {
        if (first) { first = false; throw new Error('socket closed') }
        return { ok: true, receipt_id: body.receipt_id, applied: { room_id: 'task-room' } }
      },
    })
    await settle()
    await wrapper.get('[data-testid="btn-approve-roles"]').trigger('click')
    await settle()
    expect(wrapper.get('[data-testid="action-outcome"]').text()).toContain('请求未完成')
    expect(review.mock.calls.length).toBe(1)          // 断网后保留原审阅
    expect(reviewBody).toHaveLength(1)

    await wrapper.get('[data-testid="btn-approve-roles"]').trigger('click')
    await settle()
    expect(confirm).toHaveBeenCalledTimes(2)
    expect(confirmBody[0].receipt_id).toBe(confirmBody[1].receipt_id)
    expect(confirmBody[0].decision.subject).toEqual(confirmBody[1].decision.subject)
    expect(wrapper.get('[data-testid="action-outcome"]').text()).toContain('已生效')
  })

  it('clears the old snapshot and reloads when the displayed input changes', async () => {
    const { wrapper, vm, review, setRevision, setDefer, releaseReview } = mountRoom()
    await settle()
    expect(wrapper.get('[data-testid="review-approve-roles"]').text()).toContain('本次审阅版本 r3')

    setDefer(true)
    setRevision(4)
    await vm.loadTeam(vm.roomStates['task-room'])
    await flushPromises()
    const loading = wrapper.get('[data-testid="review-approve-roles"]')
    expect(loading.text()).toContain('正在读取本次审阅内容…')
    expect(wrapper.get('[data-testid="btn-approve-roles"]').attributes('disabled')).toBeDefined()

    releaseReview({ ok: true, subject: { revision: 4 }, explanation: '审阅原文：approve-roles' })
    await settle()
    expect(wrapper.get('[data-testid="review-approve-roles"]').text()).toContain('本次审阅版本 r4')
    expect(wrapper.get('[data-testid="btn-approve-roles"]').attributes('disabled')).toBeUndefined()
    expect(review).toHaveBeenCalledTimes(2)
  })

  it('shows the plan review before enabling the first release button', async () => {
    const { wrapper, confirmBody } = mountRoom({
      noRoom: true,
      plans: [{ owner: 'S010', task: 'T-1', version: 2, title: 'F87 计划' }],
      confirm: body => ({ ok: true, receipt_id: body.receipt_id, applied: {} }),
    })
    await settle()
    const section = wrapper.get('[data-testid="plan-discovery"]')
    expect(section.text()).toContain('F87 计划')
    expect(section.text()).toContain('本次审阅版本 v2')
    expect(section.text()).toContain('审阅原文：open-plan')
    const button = section.get('button')
    expect(button.attributes('disabled')).toBeUndefined()

    await button.trigger('click')
    await settle()
    expect(confirmBody[0].action).toBe('open-plan')
    expect(confirmBody[0].input).toEqual({ owner: 'S010', task: 'T-1', version: 2 })
    expect(confirmBody[0].decision.subject).toEqual({ revision: 2 })
  })

  it('binds save-role to the reviewed edit content', async () => {
    const { wrapper, reviewBody, confirmBody } = mountRoom({
      confirm: body => ({ ok: true, receipt_id: body.receipt_id, applied: { room_id: 'task-room' } }),
    })
    await settle()
    await wrapper.findAll('.edit-role')[0].trigger('click')
    await new Promise(resolve => setTimeout(resolve, 320))
    await settle()
    expect(wrapper.get('[data-testid="review-save-role"]').text()).toContain('审阅原文：save-role')
    const input = reviewBody.at(-1)!.input
    expect(input).toEqual({
      room: 'task-room', home: 'S010', expected_revision: 1,
      role: { duty: '后端桥', arrangement: '同批', deliverables: 'bridge.py' },
    })

    await wrapper.get('.edit-actions .primary-button').trigger('click')
    await settle()
    expect(confirmBody[0].input).toEqual(input)
    expect(confirmBody[0].decision.subject).toEqual({ room: 'task-room', home: 'S010', revision: 1 })
  })

  it('binds accept-goal to the reviewed content shown for the filled form', async () => {
    const { wrapper, reviewBody, confirmBody } = mountRoom({
      approved: true,
      rolesReceipt: 'ha-' + '2'.repeat(32),
      confirm: body => ({ ok: true, receipt_id: body.receipt_id, applied: { room_id: 'task-room' } }),
    })
    await settle()
    const inputs = wrapper.findAll('[data-testid="accept-goal-form"] input')
    await inputs[0].setValue('result.md')
    await inputs[1].setValue('basis.md')
    await new Promise(resolve => setTimeout(resolve, 320))
    await settle()
    expect(wrapper.get('[data-testid="review-accept-goal"]').text()).toContain('审阅原文：accept-goal')
    expect(reviewBody.at(-1)).toEqual({
      action: 'accept-goal',
      input: { room: 'task-room', task: 'T-1', artifact: 'result.md', basis: 'basis.md', remaining: 'none', read_to: 0 },
    })

    await wrapper.get('[data-testid="btn-accept-goal"]').trigger('click')
    await settle()
    expect(confirmBody[0].input).toEqual(reviewBody.at(-1)!.input)
    expect(confirmBody[0].decision.subject).toEqual({ room: 'task-room', task: 'T-1' })
    expect(confirmBody[0].decision.channel).toBe('ui')
  })

  it('records reject/revise/defer as explicit choices, never as applied', async () => {
    const { wrapper, vm, confirmBody } = mountRoom({
      confirm: body => ({ ok: true, receipt_id: body.receipt_id, state: 'rejected', applied: null, replayed: false }),
    })
    await settle()
    await vm.teamDecide({ action: 'approve-roles', input: { room: 'task-room', expected_revision: 3 }, choice: 'reject' })
    await settle()
    expect(confirmBody[0].decision.choice).toBe('reject')
    expect(wrapper.get('[data-testid="action-outcome"]').text()).toContain('已记录：拒绝')
    expect(wrapper.get('[data-testid="team-stage"]').text()).not.toContain('已验收')
  })
})

describe('F88 grouped TODO mapping', () => {
  it('renders the backend group name, tasks and rooms without a second TODO', async () => {
    const { wrapper } = mountRoom()
    await settle()
    const group = wrapper.get('[data-testid="work-group"]')
    expect(group.text()).toContain('工作：PAOE 0.1')
    expect(group.text()).toContain('进行中 · bridge.py · 后端桥')
    expect(group.text()).toContain('CAT room-a')
    expect(wrapper.text()).not.toContain('新建 TODO')
  })
})

describe('final UI fixes (roles receipt gate + role draft retention)', () => {
  it('keeps edits made while the submitted draft is still saving', async () => {
    let finishSave: ((value: unknown) => void) | undefined
    const { wrapper } = mountRoom({
      confirm: () => new Promise(resolve => { finishSave = resolve }),
    })
    await settle()
    await wrapper.findAll('.edit-role')[0].trigger('click')
    await new Promise(resolve => setTimeout(resolve, 320))
    await settle()
    await wrapper.get('.edit-actions .primary-button').trigger('click')
    await settle()
    expect(finishSave).toBeTypeOf('function')
    await wrapper.get('[data-testid="role-edit"] input').setValue('保存期间补充的新职责')
    finishSave!({ ok: true, applied: { room_id: 'task-room' } })
    await settle()
    expect(wrapper.find('[data-testid="role-edit"]').exists()).toBe(true)
    expect((wrapper.get('[data-testid="role-edit"] input').element as HTMLInputElement).value)
      .toBe('保存期间补充的新职责')
  })

  it('hides accept-goal until the roles receipt is established and shows it after', async () => {
    const before = mountRoom({ approved: true })
    await settle()
    expect(before.wrapper.find('[data-testid="accept-goal-form"]').exists()).toBe(false)
    const after = mountRoom({ approved: true, rolesReceipt: 'ha-' + '3'.repeat(32) })
    await settle()
    expect(after.wrapper.find('[data-testid="accept-goal-form"]').exists()).toBe(true)
    expect(after.wrapper.text()).toContain('角色回执')
  })

  it('keeps the role draft on a conflicting save', async () => {
    // 默认 confirm 的 serverSubject 是 {revision:3}，与 save 的 {room,home,revision:1} 不一致 → 冲突。
    const { wrapper } = mountRoom()
    await settle()
    await wrapper.findAll('.edit-role')[0].trigger('click')
    await new Promise(resolve => setTimeout(resolve, 320))
    await settle()
    await wrapper.get('.edit-actions .primary-button').trigger('click')
    await settle()
    expect(wrapper.get('[data-testid="action-outcome"]').classes()).toContain('outcome-conflict')
    const edit = wrapper.get('[data-testid="role-edit"]')
    const inputs = edit.findAll('input')
    expect(inputs.length).toBe(3)
    expect(inputs[0].element.value).toBe('后端桥')
    expect(wrapper.get('[data-testid="review-save-role"]').text()).toContain('本次审阅版本')
  })

  it('closes the edit only after this save is explicitly applied', async () => {
    let saveApplied = false
    const { wrapper } = mountRoom({
      confirm: body => body.action !== 'save-role'
        ? { ok: true, receipt_id: body.receipt_id, applied: { room_id: 'task-room' } }
        : saveApplied
          ? { ok: true, receipt_id: body.receipt_id, applied: { room_id: 'task-room' } }
          : { ok: false, error_code: 'local_operation_failed', error: '保存失败' },
    })
    await settle()
    await wrapper.findAll('.edit-role')[0].trigger('click')
    await new Promise(resolve => setTimeout(resolve, 320))
    await settle()
    await wrapper.get('.edit-actions .primary-button').trigger('click')
    await settle()
    expect(wrapper.get('[data-testid="action-outcome"]').text()).toContain('保存失败')
    expect(wrapper.find('[data-testid="role-edit"]').exists()).toBe(true)

    saveApplied = true
    await wrapper.get('.edit-actions .primary-button').trigger('click')
    await settle()
    expect(wrapper.find('[data-testid="role-edit"]').exists()).toBe(false)
  })

  it('does not treat another action applied as this save success', async () => {
    const { wrapper } = mountRoom({
      confirm: body => ({ ok: true, receipt_id: body.receipt_id, applied: { room_id: 'task-room' } }),
    })
    await settle()
    await wrapper.findAll('.edit-role')[0].trigger('click')
    await new Promise(resolve => setTimeout(resolve, 320))
    await settle()
    // approve-roles 本次 applied 不关闭 save 编辑。
    await wrapper.get('[data-testid="btn-approve-roles"]').trigger('click')
    await settle()
    expect(wrapper.get('[data-testid="action-outcome"]').text()).toContain('已生效')
    expect(wrapper.find('[data-testid="role-edit"]').exists()).toBe(true)

    await wrapper.get('.edit-actions .primary-button').trigger('click')
    await settle()
    expect(wrapper.find('[data-testid="role-edit"]').exists()).toBe(false)
  })

  it('keeps the draft and the same receipt id for an unknown save result', async () => {
    let first = true
    const { wrapper, confirmBody } = mountRoom({
      confirm: body => {
        if (body.action !== 'save-role') return { ok: true, receipt_id: body.receipt_id, applied: { room_id: 'task-room' } }
        if (first) { first = false; throw new Error('socket closed') }
        return { ok: true, receipt_id: body.receipt_id, applied: { room_id: 'task-room' } }
      },
    })
    await settle()
    await wrapper.findAll('.edit-role')[0].trigger('click')
    await new Promise(resolve => setTimeout(resolve, 320))
    await settle()
    await wrapper.get('.edit-actions .primary-button').trigger('click')
    await settle()
    expect(wrapper.get('[data-testid="action-outcome"]').text()).toContain('请求未完成')
    expect(wrapper.find('[data-testid="role-edit"]').exists()).toBe(true)

    await wrapper.get('.edit-actions .primary-button').trigger('click')
    await settle()
    const saves = confirmBody.filter(body => body.action === 'save-role')
    expect(saves).toHaveLength(2)
    expect(saves[0].receipt_id).toBe(saves[1].receipt_id)
    expect(saves[0].decision.subject).toEqual(saves[1].decision.subject)
    expect(wrapper.find('[data-testid="role-edit"]').exists()).toBe(false)
  })
})
