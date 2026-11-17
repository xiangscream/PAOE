import { describe, expect, it, vi, afterEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ChatView from '../src/components/ChatView.vue'
import { setApiTransport } from '../src/transport'
import { bridgeTransport } from '../../../obsidian/shared/bridge'
import { buildCatUri, catRoomFromParams } from '../../../obsidian/shared/uri'

afterEach(() => setApiTransport(null))

describe('obsidian bridge adapter', () => {
  it('passes the existing API path and body to the bridge and preserves failure', async () => {
    const calls: any[] = []
    const transport = bridgeTransport({ pythonPath: 'python', installationFile: 'x', bridgePath: 'y', vaultRoot: 'z' }, async (_config, request) => {
      calls.push(request)
      return request.path === '/api/layout'
        ? { status: 200, body: { ok: true, layout: { nodes: {}, viewport: { x: 0, y: 0, zoom: 1 } } } }
        : { status: 503, body: { ok: false, error_code: 'cat_offline', error: 'CAT 离线' } }
    })
    const saved = await transport('/api/layout', { method: 'PUT', body: JSON.stringify({ project: '1001' }) })
    expect(calls[0]).toMatchObject({ method: 'PUT', path: '/api/layout', body: { project: '1001' } })
    expect(saved.ok).toBe(true)
    const failed = await transport('/api/cat/rooms')
    expect(failed.ok).toBe(false)
    expect(failed.status).toBe(503)
    expect((await failed.json()).error_code).toBe('cat_offline')
  })
})

describe('CAT protocol', () => {
  it('builds a vault-bound URI and refuses a different current vault', () => {
    const uri = buildCatUri('System', 'room-a b')
    expect(uri).toContain('obsidian://paos-cat?')
    expect(uri).toContain('vault=System')
    expect(uri).toContain('room=room-a+b')
    expect(catRoomFromParams({ vault: 'System', room: 'room-a' }, 'System')).toEqual({ room: 'room-a' })
    expect(catRoomFromParams({ vault: '6faa35d59395acfc', room: 'room-a' }, 'System', ['6faa35d59395acfc'])).toEqual({ room: 'room-a' })
    expect(catRoomFromParams({ vault: 'Other', room: 'room-a' }, 'System').room).toBe('')
  })
})

describe('embedded CAT lifecycle', () => {
  it('uses the direct CAT event URL, leaves browser history alone and closes the stream on unmount', async () => {
    history.replaceState(null, '', '/cat?room=room-a')
    const urlBefore = location.href
    const room = {
      ok: true, id: 'room-a', title: 'A 的讨论', status: 'open',
      members: [{ home_id: 'human', state: 'participant' }],
      messages: [{ id: 'm-1', seq: 1, sender_id: 'human', body: '原消息', created_at: '2026-11-07T00:00:00Z' }],
    }
    setApiTransport(async url => ({
      ok: true,
      status: 200,
      json: async () => url === '/api/cat/rooms'
        ? { ok: true, rooms: [{ id: 'room-a', title: room.title, status: 'open', created_at: '2026-11-07T00:00:00Z' }] }
        : url === '/api/cat/people' ? { ok: true, people: [] } : room,
    }))
    const close = vi.fn()
    const source = vi.fn(function (url: string) { return { url, addEventListener: vi.fn(), close } })
    vi.stubGlobal('EventSource', source)
    vi.stubGlobal('ResizeObserver', vi.fn(function () { return { observe: vi.fn(), disconnect: vi.fn() } }))
    const wrapper = mount(ChatView, {
      props: {
        project: '', initialRoom: 'room-a', embedded: true,
        eventUrl: (id: string, cursor: number) => 'http://127.0.0.1:8870/api/rooms/' + id + '/events?after=' + cursor,
      },
    })
    await flushPromises()
    expect(source).toHaveBeenCalledWith('http://127.0.0.1:8870/api/rooms/room-a/events?after=1')
    expect(location.href).toBe(urlBefore)
    expect(wrapper.text()).toContain('原消息')
    wrapper.unmount()
    expect(close).toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})
