import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import CatPanel from '../../../obsidian/system-cat/CatPanel.vue'
import ChatView from '../src/components/ChatView.vue'
import { setApiTransport } from '../src/transport'

afterEach(() => { setApiTransport(null); vi.unstubAllGlobals() })

it('keeps the requested room when the initial room list finishes after the cross-vault request', async () => {
  vi.stubGlobal('ResizeObserver', vi.fn(function () { return { observe: vi.fn(), disconnect: vi.fn() } }))
  let releaseRooms!: () => void
  const roomsReady = new Promise<void>(resolve => { releaseRooms = resolve })
  const room = (id: string) => ({
    ok: true, id, title: id, status: 'open',
    members: [{ home_id: 'human', state: 'participant' }],
    messages: [{ id: id + '-message', seq: 1, sender_id: 'human', body: id, created_at: '2026-11-17T00:00:00Z' }],
  })
  setApiTransport(async url => {
    let body: unknown
    if (url === '/api/cat/rooms') {
      await roomsReady
      body = { ok: true, rooms: [
        { id: 'room-other', title: 'Other', status: 'open', created_at: '2026-11-17T02:00:00Z' },
        { id: 'room-target', title: 'Target', status: 'open', created_at: '2026-11-17T01:00:00Z' },
      ] }
    } else if (url === '/api/cat/people') body = { ok: true, people: [] }
    else body = room(url.includes('room-target') ? 'room-target' : 'room-other')
    return { ok: true, status: 200, json: async () => body }
  })
  const wrapper = mount(CatPanel, { props: {
    project: '', initialRoom: '', eventUrl: (id: string) => id,
    streamFactory: () => ({ addEventListener: vi.fn(), close: vi.fn(), onerror: null }),
  } })
  try {
    await nextTick()
    await (wrapper.vm as any).selectRoom('room-target')
    expect((wrapper.findComponent(ChatView).vm as any).roomId).toBe('room-target')
    releaseRooms()
    await flushPromises()
    expect((wrapper.findComponent(ChatView).vm as any).roomId).toBe('room-target')
  } finally { releaseRooms(); wrapper.unmount() }
})
