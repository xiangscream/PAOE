import { spawn } from 'child_process'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { runBridge } from '../../../obsidian/shared/bridge'

vi.mock('child_process', () => {
  const spawn = vi.fn()
  return { spawn, default: { spawn } }
})

const config = { pythonPath: 'python', installationFile: 'fixture.json', bridgePath: 'bridge.py', vaultRoot: 'fixture' }

function processFixture() {
  function emitter() {
    const listeners: Record<string, (...args: any[]) => void> = {}
    return {
      on: (event: string, listener: (...args: any[]) => void) => { listeners[event] = listener },
      emit: (event: string, ...args: any[]) => listeners[event]?.(...args),
    }
  }
  const child = { ...emitter(), stdout: emitter(), stderr: emitter(), stdin: { end: vi.fn() } }
  vi.mocked(spawn).mockReturnValue(child as any)
  return child
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks() })

describe('Human confirmation bridge waiting', () => {
  it('keeps the same confirmation pending beyond 45 seconds and returns its actual result', async () => {
    const child = processFixture()
    let finished = false
    const pending = runBridge(config, { method: 'POST', path: '/api/team/confirm', body: { action: 'open-plan' } })
    pending.then(() => { finished = true })
    await vi.advanceTimersByTimeAsync(60000)
    expect(finished).toBe(false)
    expect(spawn).toHaveBeenCalledTimes(1)
    child.stdout.emit('data', new TextEncoder().encode('{"status":200,"body":{"ok":true,"state":"cancelled"}}'))
    child.emit('close', 0)
    expect(await pending).toEqual({ status: 200, body: { ok: true, state: 'cancelled' } })
  })

  it.each([{ method: 'GET', path: '/api/context' }, { method: 'POST', path: '/api/messages' }])(
    'retains the timeout for ordinary $method $path', async request => {
      processFixture()
      const pending = runBridge(config, request)
      await vi.advanceTimersByTimeAsync(45000)
      expect((await pending).body.error_code).toBe('bridge_timeout')
    },
  )
})
