import http from 'http'
import https from 'https'

export interface NativeSse {
  addEventListener(type: string, listener: (event: { data: string }) => void): void
  close(): void
  onerror: (() => void) | null
}

/**
 * Obsidian runs with Node integration. The CAT backend does not send CORS
 * headers, so a browser EventSource from app://obsidian.md cannot read it.
 * This adapter keeps the same SSE contract but reads the response natively.
 */
export function nativeEventSource(url: string): NativeSse {
  const listeners = new Map<string, Array<(event: { data: string }) => void>>()
  let request: any = null
  let retry: ReturnType<typeof setTimeout> | null = null
  let closed = false
  let abort: (() => void) | null = null
  let lastEventId = ''
  let pendingEventId: string | null = null

  const stream = {
    onerror: null as (() => void) | null,
    addEventListener(type: string, listener: (event: { data: string }) => void) {
      const list = listeners.get(type) || []
      list.push(listener)
      listeners.set(type, list)
    },
    close() {
      closed = true
      if (retry) clearTimeout(retry)
      retry = null
      abort?.()
      abort = null
      request?.destroy()
      request = null
    },
  }

  const connect = () => {
    if (closed) return
    pendingEventId = null
    let target: URL
    try { target = new URL(url) } catch { stream.onerror?.(); return }
    const client = target.protocol === 'https:' ? https : http
    const req = client.request({
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port,
      path: target.pathname + target.search,
      method: 'GET',
      headers: {
        Accept: 'text/event-stream',
        'Cache-Control': 'no-cache',
        ...(lastEventId ? { 'Last-Event-ID': lastEventId } : {}),
      },
    }, (response: any) => {
      if (closed) { response.destroy(); return }
      if (!response.statusCode || response.statusCode < 200 || response.statusCode >= 300) {
        stream.onerror?.()
        response.resume()
        schedule()
        return
      }
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      let name = 'message'
      let data: string[] = []
      const dispatch = () => {
        const payload = { data: data.join('\n') }
        const list = listeners.get(name) || []
        for (const listener of list) listener(payload)
        if (pendingEventId !== null) lastEventId = pendingEventId
        pendingEventId = null
        name = 'message'
        data = []
      }
      response.on('data', (chunk: any) => {
        buffer += decoder.decode(chunk, { stream: true })
        let index = buffer.search(/\r?\n/)
        while (index >= 0) {
          const line = buffer.slice(0, index)
          buffer = buffer.slice(index + (buffer[index] === '\r' ? 2 : 1))
          if (!line) { dispatch() }
          else if (line.startsWith(':')) { /* heartbeat */ }
          else if (line.startsWith('event:')) name = line.slice(6).trim()
          else if (line.startsWith('id:')) pendingEventId = line.slice(3).trim()
          else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
          index = buffer.search(/\r?\n/)
        }
      })
      response.on('end', () => { if (!closed) { stream.onerror?.(); schedule() } })
      response.on('error', () => { if (!closed) { stream.onerror?.(); schedule() } })
    })
    request = req
    req.on('error', () => { if (!closed) { stream.onerror?.(); schedule() } })
    req.end()
  }

  const schedule = () => {
    if (closed || retry) return
    retry = setTimeout(() => { retry = null; connect() }, 1500)
  }

  // Keep an abort hook for close(); request.destroy() is enough for http,
  // but this also stops a pending TLS handshake without global effects.
  abort = () => { request?.destroy() }
  connect()
  return stream
}
