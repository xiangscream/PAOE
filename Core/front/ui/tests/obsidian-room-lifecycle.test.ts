import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import CatPanel from '../../../obsidian/system-cat/CatPanel.vue'
import ChatView from '../src/components/ChatView.vue'
import { setApiTransport } from '../src/transport'
import http from 'http'
import { nativeEventSource } from '../../../obsidian/shared/stream'

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

it('resumes the native CAT stream from its last delivered SSE event ID', async () => {
  let resolveReconnect!: (value: string | undefined) => void
  const reconnected = new Promise<string | undefined>(resolve => { resolveReconnect = resolve })
  let connections = 0
  const server = http.createServer((request: any, response: any) => {
    connections++
    response.writeHead(200, { 'Content-Type': 'text/event-stream' })
    if (connections === 1) response.end('id: 2\nevent: room\ndata: {"cursor":2}\n\n')
    else resolveReconnect(request.headers['last-event-id'])
  })
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
  const port = (server.address() as any).port
  const stream = nativeEventSource(`http://127.0.0.1:${port}/events?after=1`)
  try {
    expect(await reconnected).toBe('2')
  } finally {
    stream.close()
    await new Promise<void>(resolve => server.close(() => resolve()))
  }
})
