import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ChatView from '../src/components/ChatView.vue'

// CAT 任务房完整交互：任务 INDEX 顶部入口、提请/确认/继续关房、human 已读游标、在线计数。
// progress 只记 human 本人；INDEX 走 /api/document（project_id + index_path）；
// 关房状态只信真实回执 value.room.status，缺字段显示未确认，不用 action 推断。
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

const members = () => [
  {home_id:'human', state:'participant', presence:'online', last_read_seq:0},
  {home_id:'S069', state:'participant', presence:'online', label:'结构文案'},
  {home_id:'S070', state:'participant', presence:'offline'},
  {home_id:'S071', state:'participant', presence:'unknown'},
  {home_id:'S072', state:'observer', presence:'online'},
]
const people = () => [{staff_number:'S069', name:'结构文案', roles:['编辑']}, {staff_number:'S070', name:'未补齐', roles:[]}]

interface CloseReceipt { ok: boolean; room?: { status?: string } }

function mountRoom(roomOverrides: Record<string, unknown> = {}, handlers: { document?: (path: string) => Promise<unknown>; closeResult?: () => CloseReceipt } = {}) {
  const room = () => ({
    ok:true, id:'task-room', title:'任务房验收', status:'open', members:members(),
    owner_id:'S069', close_policy:'human_confirm',
    task_context:{goal:'交付 CAT 任务房首版', index_path:'Works/CAT-TASKROOM-20261120/INDEX.md', project_id:'3002'},
    messages:[{id:'m1', seq:1, sender_id:'S069', body:'开工', created_at:'2026-11-20T10:00:00Z'},
              {id:'m2', seq:2, sender_id:'S070', body:'进展', created_at:'2026-11-20T11:00:00Z'}],
    ...roomOverrides,
  })
  const progress = vi.fn(async (_p: string, _o?: RequestInit) => ({ok:true}))
  const close = vi.fn(async (_p: string, options?: RequestInit): Promise<CloseReceipt> => {
    const {action} = JSON.parse(String(options?.body)) as {action: string}
    return handlers.closeResult ? handlers.closeResult() : {ok:true, room:{status: action==='confirm' ? 'closed' : 'open'}}
  })
  const document_ = handlers.document || vi.fn(async (_p: string) => ({ok:true, path:'Works/CAT-TASKROOM-20261120/INDEX.md', body:'# INDEX\n\n- 目标：交付首版\n- 下一步：验收'}))
  const fetch = vi.fn(async (path: string, options?: RequestInit) => {
    if (options?.method === 'POST' && path.endsWith('/progress')) return {ok:true, json:async () => progress(path, options)}
    if (options?.method === 'POST' && path.endsWith('/close')) return {ok:true, json:async () => close(path, options)}
    if (path.startsWith('/api/document')) return {ok:true, json:async () => document_(path)}
    if (path.startsWith('/api/cat/rooms')) return {ok:true, json:async () => ({ok:true, rooms:[{id:'task-room', title:'任务房验收', status:room().status, created_at:'2026-11-20T00:00:00Z'}]})}
    if (path === '/api/cat/people') return {ok:true, json:async () => ({ok:true, people:people()})}
    if (path.startsWith('/api/room/')) return {ok:true, json:async () => room()}
    return {ok:true, json:async () => ({ok:true})}
  })
  vi.stubGlobal('fetch', fetch)
  vi.stubGlobal('EventSource', vi.fn(function () { return {addEventListener:vi.fn(), close:vi.fn()} }))
  vi.stubGlobal('ResizeObserver', vi.fn(function () { return {observe:vi.fn(), disconnect:vi.fn()} }))
  const wrapper = mount(ChatView, {props:{project:'3002', initialRoom:'task-room'}})
  const state = () => (wrapper.vm as unknown as {roomStates: Record<string, {status: string}>}).roomStates['task-room']
  return {wrapper, fetch, progress, close, room, state}
}

it('shows the task INDEX at the top with owner and renders the project document', async () => {
  const {wrapper} = mountRoom()
  await flushPromises()
  const index = wrapper.get('[data-testid="task-index"]')
  expect(index.text()).toContain('任务 INDEX')
  expect(index.text()).toContain('目标：交付首版')
  expect(wrapper.get('[data-testid="owner-chip"]').text()).toContain('负责人 · S069')
  expect(wrapper.findAll('.room-tabs button').map(item => item.text())).toEqual(['进行中', '待确认', '已结束'])
  await index.get('.task-index-toggle').trigger('click')
  expect(index.classes()).toContain('collapsed')
})

it('keeps the room usable when the INDEX cannot be read', async () => {
  const {wrapper} = mountRoom({}, {document: vi.fn(async () => ({ok:false, error:'document_missing'}))})
  await flushPromises()
  expect(wrapper.get('[data-testid="task-index"]').text()).toContain('暂不可读')
})

it('pending_close shows the confirmation banner and continues or closes through the bridge', async () => {
  const {wrapper, close, state} = mountRoom({status:'pending_close'})
  await flushPromises()
  const banner = wrapper.get('[data-testid="close-banner"]')
  expect(banner.text()).toContain('负责人已提请关闭')
  await banner.get('.close-banner-actions .secondary-button').trigger('click')
  await flushPromises()
  expect(JSON.parse(close.mock.calls.at(-1)![1]!.body as string)).toEqual({action:'continue'})
  // 继续讨论后横幅消失、房间回到可发言；负责人再次提请时横幅重现，Human 可确认关闭。
  expect(wrapper.find('[data-testid="close-banner"]').exists()).toBe(false)
  state()!.status='pending_close'
  await flushPromises()
  const again = wrapper.get('[data-testid="close-banner"]')
  await again.get('.close-banner-actions .primary-button').trigger('click')
  await flushPromises()
  expect(JSON.parse(close.mock.calls.at(-1)![1]!.body as string)).toEqual({action:'confirm'})
  expect(state()!.status).toBe('closed')
})

it('a close receipt without room.status shows unconfirmed instead of guessing the state', async () => {
  const {wrapper, state} = mountRoom({status:'pending_close'}, {closeResult: () => ({ok:true})})
  await flushPromises()
  await wrapper.get('[data-testid="close-banner"] .close-banner-actions .primary-button').trigger('click')
  await flushPromises()
  expect(state()!.status).toBe('pending_close')                    // 不用 action 推断 closed
  expect(wrapper.text()).toContain('结果未确认')
})

it('advances only the human read cursor, once per new sequence, and marks online', async () => {
  const {wrapper, progress} = mountRoom()
  await flushPromises()
  const bodies = () => progress.mock.calls.map(([, options]) => JSON.parse(String(options!.body)) as Record<string, unknown>)
  expect(bodies().filter(payload => 'last_read_seq' in payload)).toEqual([{presence:'online', last_read_seq:2}])
  wrapper.vm.scrollBottom()
  await flushPromises()
  expect(bodies().filter(payload => 'last_read_seq' in payload)).toHaveLength(1)
})

it('counts online task-group members for the header summary', async () => {
  const {wrapper} = mountRoom()
  await flushPromises()
  expect(wrapper.get('.members-button').text()).toContain('1 在线')   // 任务组口径：S069 在线；human 自身与旁听不计
})
