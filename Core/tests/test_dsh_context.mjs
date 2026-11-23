import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate as nextTick } from 'node:timers/promises'
import { registerContextHooks } from '../code/personal-agent-os/adapters/dsh/session.mjs'

function harness() {
  const hooks = new Map(), observed = [], stops = [], followups = [], steering = [], warnings = []
  const marked = new WeakSet()
  const surface = []
  const signal = new AbortController().signal
  let serial = 0
  const createUserMessage = value => ({ ...value, id: 'm' + ++serial, role: 'user' })
  const fixture = {
    phaseReads: 0, nativeCalls: 0, compactions: 0, total: 30, window: 100, selectedCost: 5,
    version: '1:12', task: 'T1', stopFile: false, modelReplied: false,
  }
  const agent = { session: { id: 'own-session', deriveMessages: () => surface }, status: 'running',
    followup: message => followups.push(message), steer: message => steering.push(message) }
  const ctx = {
    get: key => ctx[key],
    on: (event, listener) => hooks.set(event, listener),
    effect: init => { fixture.dispose = init() },
    logger: { warn: (...args) => warnings.push(args) },
    llm: { resolveModelInfo: async () => ({ context: { contextWindow: fixture.window }, defaultMaxTokens: 2 }) },
    tokenMeter: { measure: () => ({ totalTokens: fixture.total, nodes: surface.map(() => ({ tokens: fixture.selectedCost })) }) },
    compaction: { compactNow: async actual => {
      assert.equal(actual, agent)
      assert.equal(agent.status, 'idle')
      fixture.compactions++
      return { summarySeq: 27 }
    } },
  }
  const core = {
    contact: async (target, id) => {
      assert.equal(id, agent.session.id)
      assert.equal(target.home, 'S841')
      if (fixture.unbound) throw new Error('Contact does not match')
      return { stopped: fixture.stopFile, stopFile: 'stop' }
    },
    currentVersion: async () => fixture.version,
    stopped: async () => fixture.stopFile,
    phase: async () => {
      fixture.phaseReads++
      if (fixture.missing) throw new Error('required approval.md missing')
      return { task_id: fixture.task, documents: [
        { kind: 'current', path: 'TODO.md', version: fixture.version, body: 'Original work' },
        { kind: 'background', path: 'context.md', version: '1', body: 'background tail marker' },
        ...(fixture.role ? [{ kind: 'active_role', path: 'cat-role:room-1', version: fixture.role, body: 'Role ' + fixture.role }] : []),
      ] }
    },
    rolesChanged: async roles => roles[0].version !== fixture.role,
    stop: async (_target, event, task, flags) => {
      stops.push({ event, task, flags })
      return { action: flags.length ? 'stop' : 'continue', next_action: 'Finish the original work' }
    },
    observe: async (_target, record) => { observed.push(record) },
  }
  registerContextHooks(ctx, { 'own-session': { project: '3997', home: 'S841' } }, core,
    { createUserMessage, isAgentLoopRequest: request => marked.has(request) })
  hooks.get('agent/created')({ agent, source: 'startup' })
  const direct = createUserMessage({ source: { kind: 'user' }, content: [{ type: 'text', text: 'Do the original task' }] })
  async function enter(messages, turn = 1, step = 1) {
    const decision = await hooks.get('agent/pre-step')({ agent, messages, turn, step, signal },
      async () => ({ kind: 'enter', messages }))
    surface.push(...decision.messages)
    return decision.messages
  }
  async function request({ messages = surface, purpose, loop = true, id = agent.session.id } = {}) {
    const options = Object.freeze({ messages: Object.freeze([...messages]), sessionId: id, purpose,
      provider: 'test', model: 'current-model', signal })
    if (loop) marked.add(options)
    const stream = hooks.get('llm/stream')(options, async function* () { fixture.nativeCalls++; yield 'model' })
    return Array.fromAsync(stream)
  }
  return { ctx, fixture, hooks, agent, signal, surface, direct, observed, stops, followups, steering, warnings, enter, request }
}

test('keeps the complete original and reuses a single frame on successive steps', async () => {
  const h = harness()
  const entered = await h.enter([h.direct])
  assert.match(entered[1].content[0].text, /background tail marker$/)
  assert.deepEqual(await h.request(), ['model'])
  assert.deepEqual(await h.enter([], 1, 2), [])
  assert.equal(h.fixture.phaseReads, 1)
  assert.deepEqual(await h.request(), ['model'])
  assert.equal(h.observed.at(-1).frameId, entered[1].id)
  assert.equal(JSON.stringify(h.observed).includes('Do the original task'), false)
  assert.deepEqual(h.observed.at(-1).inputIds, [h.direct.id])
})

test('checks the actual loop request and distinguishes native compaction from other calls', async () => {
  const h = harness()
  await h.enter([h.direct])
  await assert.rejects(h.request({ messages: [h.direct] }), /lacks current PAOE originals/)
  assert.equal(h.fixture.nativeCalls, 0)
  await assert.rejects(h.request({ messages: [], loop: false, purpose: 'title' }), /task is blocked/)
  assert.deepEqual(await h.request({ messages: [], loop: false, purpose: 'compaction' }), ['model'])
  await assert.rejects(h.request({ messages: [], loop: false }), /Unmarked/)
  assert.deepEqual(await h.request({ messages: [], id: 'other-session' }), ['model'])
  assert.equal(h.observed.filter(x => x.action === 'native_compaction_request').length, 1)
})

test('reads a new stage after compaction and restores the original input as attributed context', async () => {
  const h = harness()
  await h.enter([h.direct])
  h.surface.length = 0
  h.hooks.get('session/event')(h.agent.session, { type: 'compaction/summary', data: {} })
  const added = await h.enter([], 1, 2)
  assert.equal(h.fixture.phaseReads, 2)
  assert.equal(added[0].source.kind, 'paoe-context')
  assert.equal(added[1].source.originalId, h.direct.id)
  await h.request()
  h.fixture.version = '2:13'
  h.fixture.missing = true
  await assert.rejects(h.enter([], 1, 3), /approval.md/)
})

test('recovery only runs at idle once and retains the same task and model selection', async () => {
  const h = harness()
  await h.enter([h.direct])
  h.fixture.total = 150
  await assert.rejects(h.request(), /after idle/)
  assert.equal(h.fixture.compactions, 0)
  const stopping = h.hooks.get('agent/turn-stopping')
  await stopping({ agent: h.agent, turn: 1, signal: h.signal })
  assert.deepEqual(h.stops, [{ event: 'dsh:own-session:1', task: 'T1', flags: ['--presence-only'] }])
  assert.equal(h.steering.length, 0)
  h.agent.status = 'idle'
  h.hooks.get('agent/status')({ agent: h.agent, status: 'idle' })
  await nextTick()
  assert.equal(h.fixture.compactions, 1)
  assert.equal(h.followups.length, 1)
  assert.match(h.followups[0].content[0].text, /T1/)
  await h.enter(h.followups, 2)
  await assert.rejects(h.request(), /recovery: owner/)
  h.hooks.get('agent/status')({ agent: h.agent, status: 'idle' })
  await nextTick()
  assert.equal(h.fixture.compactions, 1)
})

test('a Web agent uses its retained preset compactor, independently of the Host service', async () => {
  const h = harness()
  const engine = h.ctx.compaction
  delete h.ctx.compaction
  h.ctx.agentPresets = { composedPreset: () => 'standard', serviceFor: (agent, name) => {
    assert.equal(agent, h.agent)
    assert.equal(name, 'compaction')
    return engine
  } }
  await h.enter([h.direct])
  h.fixture.total = 150
  await assert.rejects(h.request(), /after idle/)
  h.agent.status = 'idle'
  h.hooks.get('agent/status')({ agent: h.agent, status: 'idle' })
  await nextTick()
  assert.equal(h.fixture.compactions, 1)
  assert.equal(h.followups.length, 1)
})

test('a preset without native compaction reports its own scope before the provider runs', async () => {
  const h = harness()
  h.ctx.agentPresets = { composedPreset: () => 'minimal-custom', serviceFor: () => undefined }
  await assert.rejects(h.enter([h.direct]), /compaction is unavailable in minimal-custom for S841/)
  assert.equal(h.observed.at(-1).action, 'compaction_unavailable')
  assert.equal(h.observed.at(-1).scope, 'minimal-custom')
  assert.equal(h.fixture.compactions, 0)
  assert.equal(h.fixture.nativeCalls, 0)
})

test('a headless host missing the compaction capability stops before the provider runs', async () => {
  const h = harness()
  delete h.ctx.compaction
  await assert.rejects(h.enter([h.direct]), /compaction is unavailable in host for S841/)
  assert.equal(h.observed.at(-1).action, 'compaction_unavailable')
  assert.equal(h.fixture.nativeCalls, 0)
})

test('an interrupted or oversized current task never schedules a new turn', async () => {
  for (const state of ['interrupted', 'selected-too-large', 'stopped']) {
    const h = harness()
    await h.enter([h.direct])
    h.fixture.total = 150
    if (state === 'selected-too-large') h.fixture.selectedCost = 60
    await assert.rejects(h.request(), /exceeds capacity/)
    if (state === 'interrupted') {
      h.hooks.get('session/event')(h.agent.session, { type: 'turn/end', data: { turn: 1, reason: { kind: 'aborted' } } })
    }
    if (state === 'stopped') h.fixture.stopFile = true
    h.agent.status = 'idle'
    h.hooks.get('agent/status')({ agent: h.agent, status: 'idle' })
    await nextTick()
    assert.equal(h.fixture.compactions, 0)
    assert.equal(h.followups.length, 0)
  }
})

test('one normal stop can steer once; a second stop, unregistered session and STOP preserve original control', async () => {
  const h = harness()
  await h.enter([h.direct])
  await h.request()
  const handle = h.hooks.get('agent/turn-stopping'), event = { agent: h.agent, turn: 1, signal: h.signal }
  await handle(event)
  await handle(event)
  assert.equal(h.steering.length, 1)
  assert.deepEqual(h.stops.map(s => s.flags), [[], ['--reentry']])
  h.fixture.stopFile = true
  await handle(event)
  assert.deepEqual(h.stops.at(-1).flags, ['--presence-only'])
  assert.equal(h.steering.length, 1)
  const changed = harness()
  changed.fixture.unbound = true
  await assert.rejects(changed.enter([changed.direct]), /Contact/)
})

test('a missing original or initially stopped Home leaves once without starting business work', async () => {
  for (const mode of ['missing', 'stopFile']) {
    const h = harness()
    h.fixture[mode] = true
    if (mode === 'missing') await assert.rejects(h.enter([h.direct]), /approval.md/)
    else await h.enter([h.direct])
    const stop = h.hooks.get('agent/turn-stopping')
    const event = { agent: h.agent, turn: 1, signal: h.signal }
    await stop(event)
    await stop(event)
    h.hooks.get('session/event')(h.agent.session, { type: 'turn/end', data: { turn: 1, reason: { kind: 'interrupted' } } })
    await nextTick()
    assert.deepEqual(h.stops, [{ event: 'dsh:own-session:1', task: '', flags: ['--presence-only'] }])
    assert.equal(h.steering.length, 0)
    assert.equal(h.followups.length, 0)
  }
})

test('unknown model capacity stays unknown and does not manufacture a threshold', async () => {
  const h = harness()
  h.fixture.window = undefined
  await h.enter([h.direct])
  await h.request()
  assert.equal(h.observed.at(-1).contextWindow, null)
})

test('a registered role update reloads the new text while an unchanged role reuses the current frame', async () => {
  const h = harness()
  h.fixture.role = '1'
  await h.enter([h.direct])
  await h.request()
  assert.equal((await h.enter([], 1, 2)).length, 0)
  assert.equal(h.fixture.phaseReads, 1)
  h.fixture.role = '2'
  const [updated] = await h.enter([], 1, 3)
  assert.match(updated.content[0].text, /Role 2/)
  assert.equal(h.fixture.phaseReads, 2)
})
