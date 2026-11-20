import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ChatView from '../src/components/ChatView.vue'

// CAT 任务房首片：选人、收件范围预览、点名发送与房外邀请。
// preview 与 send 只信后台返回；正文 @ 仅是给读者的提示，不参与收件计算。
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

const members = () => [
  {home_id:'human', state:'participant', presence:'online'},
  {home_id:'S069', state:'participant', presence:'online', label:'结构文案'},
  {home_id:'S070', state:'participant', presence:'offline'},
  {home_id:'S071', state:'participant'},                          // 旧房：unknown
  {home_id:'S072', state:'observer', presence:'online'},          // 旁听：不在任务组
  {home_id:'S073', state:'left', presence:'online'},
]
const people = () => [
  {staff_number:'S069', name:'结构文案', roles:['编辑']},
  {staff_number:'S070', name:'未补齐', roles:[]},
  {staff_number:'S071', name:'资料员', roles:['查证']},
  {staff_number:'S072', name:'旁听员', roles:[]},
  {staff_number:'S080', name:'编外顾问', roles:['咨询']},
]

function mountRoom(overrides = {}) {
  const preview = vi.fn(async (path: string, options?: RequestInit) => {
    const {target_ids} = JSON.parse(String(options?.body))
    return target_ids?.length
      ? {ok:true, recipient_mode:'selected', recipients:target_ids}
      : {ok:true, recipient_mode:'all', recipients:['human','S069','S070','S071']}
  })
  const send = vi.fn(async (_path: string, _options?: RequestInit) => ({ok:true, accepted:true, dispatch:'queued', message:{id:'m1', seq:1, sender_id:'human', body:'x', created_at:'2026-11-20T12:00:00Z'}, recipients:['S069','S070']}))
  const fetch = vi.fn(async (path: string, options?: RequestInit) => {
    if (options?.method === 'POST' && path.endsWith('/message-preview')) return {ok:true, json:async () => preview(path, options)}
    if (options?.method === 'POST' && path.endsWith('/message')) return {ok:true, json:async () => send(path, options)}
    if (path.startsWith('/api/cat/rooms')) return {ok:true, json:async () => ({ok:true, rooms:[{id:'task-room', title:'任务房', status:'open', created_at:'2026-11-20T00:00:00Z'}]})}
    if (path === '/api/cat/people') return {ok:true, json:async () => ({ok:true, people:people()})}
    return {ok:true, json:async () => ({ok:true, id:'task-room', title:'任务房', status:'open', members:members(), messages:[]})}
  })
  vi.stubGlobal('fetch', fetch)
  vi.stubGlobal('EventSource', vi.fn(function () { return {addEventListener:vi.fn(), close:vi.fn()} }))
  vi.stubGlobal('ResizeObserver', vi.fn(function () { return {observe:vi.fn(), disconnect:vi.fn()} }))
  const wrapper = mount(ChatView, {props:{project:'3002', initialRoom:'task-room'}, ...overrides})
  return {wrapper, fetch, preview, send}
}

it('shows the room-wide scope with the observer note once composing starts', async () => {
  const {wrapper} = mountRoom()
  await flushPromises()
  await wrapper.get('.composer form').trigger('focusin')
  await flushPromises()
  const scope = wrapper.get('[data-testid="scope-line"]')
  expect(scope.text()).toBe('提醒全房 · 4 位成员 · 另有 1 位旁听不在提醒范围')
})

it('picks task-group members only, previews and sends target_ids; body @ stays cosmetic', async () => {
  vi.useFakeTimers()
  try {
    const {wrapper, preview, send} = mountRoom()
    await flushPromises()
    await wrapper.get('.mention-toggle').trigger('click')
    await flushPromises()
    const panel = wrapper.get('.mention-panel')
    // 在线在前、状态未知次之、离线最后；旁听/退席/human 不进候选。
    expect(panel.findAll('.mention-list button').map(item => item.find('strong')!.text()))
      .toEqual(['S069 · 结构文案', 'S071 · 资料员', 'S070 · 未补齐'])
    await panel.findAll('.mention-list button')[0].trigger('click')   // S069（在线）
    await panel.findAll('.mention-list button')[2].trigger('click')   // S070（离线 · 将唤醒）
    await flushPromises()
    // 收件人只来自选择；正文里插入的 @ 只是提示。
    expect(wrapper.get('.target-chips').text()).toContain('S069')
    expect(wrapper.get('.target-chips').text()).toContain('S070')
    expect((wrapper.get('#message-input').element as HTMLTextAreaElement).value).toContain('@')
    vi.advanceTimersByTime(400); await flushPromises()
    expect(preview).toHaveBeenCalled()
    expect(JSON.parse(preview.mock.calls.at(-1)![1]!.body as string)).toEqual({target_ids:['S069','S070']})
    expect(wrapper.get('[data-testid="scope-line"]').text()).toBe('点名提醒 2 人')
    vi.useRealTimers()
    await wrapper.get('#message-input').setValue('按新口径继续')
    await wrapper.get('.composer form').trigger('submit')
    await flushPromises()
    const payload = JSON.parse(send.mock.calls.at(-1)![1]!.body as string)
    expect(payload.target_ids).toEqual(['S069','S070'])
    expect(payload.body).toContain('按新口径继续')
    // 发送成功后选择清空，范围回到全房预览。
    expect(wrapper.find('.target-chips').exists()).toBe(false)
  } finally { vi.useRealTimers() }
})

it('unselecting a picked member removes the chip and does not append another body @', async () => {
  const {wrapper} = mountRoom()
  await flushPromises()
  await wrapper.get('.mention-toggle').trigger('click')
  const panel = wrapper.get('.mention-panel')
  await panel.findAll('.mention-list button')[0].trigger('click')   // 选 S069
  await flushPromises()
  const atCount = () => (wrapper.get('#message-input').element as HTMLTextAreaElement).value.split('@').length - 1
  const afterFirst = atCount()
  await panel.findAll('.mention-list button')[0].trigger('click')   // 取消 S069
  await flushPromises()
  expect(wrapper.find('.target-chips').exists()).toBe(false)
  expect(atCount()).toBe(afterFirst)                                 // 取消不再追加正文 @
})

it('invites an outside colleague through invite:true with only that target', async () => {
  const {wrapper, send} = mountRoom()
  await flushPromises()
  await wrapper.get('.mention-toggle').trigger('click')
  const outsideTab = wrapper.findAll('.mention-tabs button').find(item => item.text() === '房外邀请')!
  await outsideTab.trigger('click')
  const search = wrapper.get('.mention-search input')
  await search.setValue('编外')
  await flushPromises()
  expect(wrapper.get('.mention-panel').text()).toContain('S080')
  expect(wrapper.get('.mention-panel').text()).not.toContain('S069')   // 在房者不进房外候选
  await search.trigger('keydown', {key:'Enter'})
  await flushPromises()
  const payload = JSON.parse(send.mock.calls.at(-1)![1]!.body as string)
  expect(payload.invite).toBe(true)
  expect(payload.target_ids).toEqual(['S080'])
  expect(payload.body).toContain('邀请')
})

it('roster sheet labels observers as 旁听，不在任务组 and keeps offline wake hints', async () => {
  const {wrapper} = mountRoom()
  await flushPromises()
  // memberDialog 为原生 <dialog>，其内容始终在 DOM 中，可直接断言名册行。
  const rows = wrapper.findAll('.member-row')
  expect(rows.length).toBe(6)
  const observer = rows.find(row => row.text().includes('S072'))!
  expect(observer.text()).toContain('旁听，不在任务组')
  const offline = rows.find(row => row.text().includes('S070'))!
  expect(offline.text()).toContain('将唤醒')
  const unknown = rows.find(row => row.text().includes('S071'))!
  expect(unknown.text()).toContain('状态未知')
})
