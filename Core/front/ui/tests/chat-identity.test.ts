import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ChatView from '../src/components/ChatView.vue'

afterEach(() => vi.unstubAllGlobals())

async function emptyChat() {
  const fetch = vi.fn(async (path: string) => ({
    ok: true,
    json: async () => path.startsWith('/api/cat/rooms') ? { ok: true, rooms: [] } : { ok: true, people: [] },
  }))
  vi.stubGlobal('fetch', fetch)
  vi.stubGlobal('EventSource', vi.fn(function () { return { addEventListener: vi.fn(), close: vi.fn() } }))
  vi.stubGlobal('ResizeObserver', vi.fn(function () { return { observe: vi.fn(), disconnect: vi.fn() } }))
  const wrapper = mount(ChatView, { props: { project: '3002' } })
  await flushPromises()
  return wrapper
}

it('uses the global staff number as the CAT primary label, even for an old Home-id label', async () => {
  history.replaceState(null, '', '/cat?room=room-one')
  const fetch = vi.fn(async (path: string) => ({
    ok: true,
    json: async () => path.startsWith('/api/cat/rooms')
      ? { ok: true, rooms: [{ id: 'room-one', title: '测试讨论', status: 'open', created_at: '2026-11-07T00:00:00Z' }] }
      : path === '/api/cat/people'
        ? { ok: true, people: [{ id: '3002-s035', number: 'S040', name: 'S040 · 前端', role: '前端' }] }
        : { ok: true, id: 'room-one', title: '测试讨论', status: 'open', members: [{ home_id: '3002-s035', label: '3002-s035', state: 'participant' }], messages: [] },
  }))
  vi.stubGlobal('fetch', fetch)
  vi.stubGlobal('EventSource', vi.fn(function () { return { addEventListener: vi.fn(), close: vi.fn() } }))
  vi.stubGlobal('ResizeObserver', vi.fn(function () { return { observe: vi.fn(), disconnect: vi.fn() } }))
  const wrapper = mount(ChatView, { props: { project: '3002', initialRoom: 'room-one' } })
  await flushPromises()
  expect(wrapper.text()).toContain('S040')
  expect(wrapper.text()).not.toContain('3002-s035')
  expect((wrapper.vm as any).name('3002-s035')).toBe('S040 · 前端')
  wrapper.unmount()
})

it('shows the global number when the person name is empty and the room label is a Home id', async () => {
  const wrapper = await emptyChat()
  const vm = wrapper.vm as any
  vm.people = [{ id: '3002-s035', number: 'S040', name: '' }]
  vm.roomId = 'room-one'
  vm.roomStates['room-one'] = { members: [{ home_id: '3002-s035', label: '3002-s035' }] }
  expect(vm.name('3002-s035')).toBe('S040')
  wrapper.unmount()
})

it('does not show a legacy Home label after the member id becomes S040', async () => {
  const wrapper = await emptyChat()
  const vm = wrapper.vm as any
  vm.people = [{ id: 'S040', number: 'S040', name: '' }]
  vm.roomId = 'room-one'
  vm.roomStates['room-one'] = { members: [{ home_id: 'S040', label: '3002-s035' }] }
  expect(vm.name('S040')).toBe('S040')
  wrapper.unmount()
})

it('marks missing numbers explicitly instead of showing a Home id', async () => {
  const wrapper = await emptyChat()
  const vm = wrapper.vm as any
  vm.people = [{ id: '3002-s035', number: '', name: '' }]
  vm.roomId = 'room-one'
  vm.roomStates['room-one'] = { members: [{ home_id: '3002-s035', label: '3002-s035' }] }
  expect(vm.name('3002-s035')).toBe('员工资料未补齐')

  vm.roomStates['room-one'] = { members: [{ home_id: '3002-s035', label: '前端' }] }
  expect(vm.name('3002-s035')).toBe('未编号 · 前端')

  vm.roomStates['room-one'] = { members: [{ home_id: '3002-s035', label: '3002-s035' }] }
  vm.people = [{ id: '3002-s035', number: '', name: '前端' }]
  expect(vm.name('3002-s035')).toBe('未编号 · 前端')
  wrapper.unmount()
})
