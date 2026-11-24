// The callbacks below are test-driven. Message objects and the request brand are the installed host's.
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { apply } from '../code/personal-agent-os/adapters/dsh/index.mjs'

const [installation, python] = process.argv.slice(2)
const host = createRequire(join(process.env.DSH_INSTALL_DIR, 'package.json'))
const loop = createRequire(host.resolve('@deepseek-ai/dsh-agent-loop'))
const sdk = await import(pathToFileURL(loop.resolve('@deepseek-ai/dsh-llm')).href)
const hooks = new Map(), surface = []
const ctx = {
  get(name) { return this[name] },
  on: (key, fn) => hooks.set(key, fn),
  effect: fn => fn(),
  logger: { warn: (...args) => { throw new Error(args.join(' ')) } },
  llm: { resolveModelInfo: async () => ({ context: { contextWindow: 32000 } }) },
  tokenMeter: { measure: () => ({ totalTokens: 100, nodes: surface.map(() => ({ tokens: 10 })) }) },
  compaction: { compactNow() { assert.fail('The under-capacity pair must not compact') } },
}
const agent = { session: { id: 'fixture-dsh-session', deriveMessages: () => surface }, status: 'running' }
const signal = new AbortController().signal
await apply(ctx, { installation, python, sessions: { 'fixture-dsh-session': { home: 'S841', project: '3997' } } })
hooks.get('agent/created')({ agent, source: 'resume', signal })
const input = sdk.createUserMessage({ content: [{ type: 'text', text: 'Synthetic job' }], source: { kind: 'user' } })
for (const step of [1, 2]) {
  const messages = step === 1 ? [input] : []
  const decision = await hooks.get('agent/pre-step')({ agent, turn: 1, step, messages, signal }, async () => ({ kind: 'enter', messages }))
  if (step === 2) assert.equal(decision.messages.length, 0)
  surface.push(...decision.messages)
  const frame = surface.find(m => m.source?.kind === 'paoe-context')
  assert.match(frame.content[0].text, /TASK-ORIGINAL-END/)
  assert.match(frame.content[0].text, /SYNTHETIC-BACKGROUND-END/)
  const request = sdk.markAgentLoopRequest(Object.freeze({ sessionId: agent.session.id, messages: Object.freeze([...surface]), signal,
    provider: 'fixture', model: 'fixture' }))
  const result = hooks.get('llm/stream')(request, async function* () { yield 'verified-without-provider' })
  assert.deepEqual(await Array.fromAsync(result), ['verified-without-provider'])
}
