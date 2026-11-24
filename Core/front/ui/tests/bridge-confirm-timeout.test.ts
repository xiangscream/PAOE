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

describe('bridge request timeout', () => {
  it.each([
    { method: 'POST', path: '/api/team/confirm' },
    { method: 'GET', path: '/api/context' },
    { method: 'POST', path: '/api/messages' },
  ])('ends $method $path at 45 seconds', async request => {
    processFixture()
    let finished = false
    const pending = runBridge(config, request)
    pending.then(() => { finished = true })
    await vi.advanceTimersByTimeAsync(44999)
    expect(finished).toBe(false)
    await vi.advanceTimersByTimeAsync(1)
    expect((await pending).body.error_code).toBe('bridge_timeout')
  })
})
