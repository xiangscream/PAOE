import { describe, expect, it, vi, afterEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ChatView from '../src/components/ChatView.vue'
import { setApiTransport } from '../src/transport'
import { bridgeTransport, runBridge } from '../../../obsidian/shared/bridge'
import { buildCatUri, catRoomFromParams } from '../../../obsidian/shared/uri'
import { nativeEventSource } from '../../../obsidian/shared/stream'
import http from 'http'
import { mkdtempSync, rmSync, writeFileSync } from 'fs'
import os from 'os'
import path from 'path'

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

  it('uses UTF-8 Python output and decodes Chinese split across child chunks', async () => {
    const dir = mkdtempSync(path.join(os.tmpdir(), 'paos-bridge-'))
    const script = path.join(dir, 'bridge.py')
    writeFileSync(script, [
      'import sys, time',
      'sys.stdin.read()',
      'sys.stdout.write(\'{"status":200,"body":{"ok":true,"text":"中文\')',
      'sys.stdout.flush()',
      'time.sleep(0.05)',
      'sys.stdout.write(\'回执"}}\')',
      'sys.stdout.flush()',
    ].join('\n'), 'utf8')
    try {
      const response = await runBridge({ pythonPath: 'python', installationFile: 'x', bridgePath: script, vaultRoot: 'x' }, { method: 'GET', path: '/api/context' })
      expect(response.status).toBe(200)
      expect(response.body.text).toBe('中文回执')
    } finally {
      rmSync(dir, { recursive: true, force: true })
    }
  })

  it('rejects extra stdout instead of guessing a JSON line', async () => {
    const dir = mkdtempSync(path.join(os.tmpdir(), 'paos-bridge-'))
    const script = path.join(dir, 'bridge.py')
    writeFileSync(script, [
      'import sys',
      'sys.stdin.read()',
      'sys.stdout.write(\'noise\\n{"status":200,"body":{"ok":true}}\')',
    ].join('\n'), 'utf8')
    try {
      const response = await runBridge({ pythonPath: 'python', installationFile: 'x', bridgePath: script, vaultRoot: 'x' }, { method: 'GET', path: '/api/context' })
      expect(response.status).toBe(0)
      expect(response.body.error_code).toBe('bridge_invalid_output')
    } finally {
      rmSync(dir, { recursive: true, force: true })
    }
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

it('consumes an SSE stream without CORS headers through the native adapter', async () => {
  const server = http.createServer((_request: any, response: any) => {
    response.writeHead(200, { 'Content-Type': 'text/event-stream; charset=utf-8' })
    response.write('event: room\ndata: {"ok":true}\n\n')
  })
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
  const address = server.address() as any
  const source = nativeEventSource(`http://127.0.0.1:${address.port}/api/rooms/room-a/events?after=0`)
  const payload = await new Promise<string>(resolve => source.addEventListener('room', event => resolve(event.data)))
  expect(payload).toBe('{"ok":true}')
  source.close()
  await new Promise<void>(resolve => server.close(() => resolve()))
})

it('does not commit a partial SSE event id before the full event is delivered', async () => {
  let connections = 0
  let resolveSecond!: (id: string | undefined) => void
  let resolveThird!: (id: string | undefined) => void
  const second = new Promise<string | undefined>(resolve => { resolveSecond = resolve })
  const third = new Promise<string | undefined>(resolve => { resolveThird = resolve })
  const server = http.createServer((request: any, response: any) => {
    connections++
    response.writeHead(200, { 'Content-Type': 'text/event-stream' })
    if (connections === 1) {
      response.end('id: 1\nevent: room\ndata: {"cursor":1}\n\nid: 2\n')
    } else if (connections === 2) {
      resolveSecond(request.headers['last-event-id'])
      response.end('id: 2\nevent: room\ndata: {"cursor":2}\n\n')
    } else {
      resolveThird(request.headers['last-event-id'])
      response.end()
    }
  })
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
  const address = server.address() as any
  const stream = nativeEventSource(`http://127.0.0.1:${address.port}/events?after=0`)
  try {
    expect(await second).toBe('1')
    expect(await third).toBe('2')
    stream.close()
    await new Promise(resolve => setTimeout(resolve, 100))
    expect(connections).toBe(3)
  } finally {
    stream.close()
    await new Promise<void>(resolve => server.close(() => resolve()))
  }
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
