import { appendFile, mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { PaosCore } from '../dsh/paos-core.mjs'

const id = 'paoe.context'
const started = 'session.execution.started'
const interrupted = 'session.execution.interrupted'
const eventTypes = [
  'session.compaction.started', 'session.compaction.ended', started, interrupted,
  'session.execution.failed', 'session.execution.succeeded',
]

async function contact(core, target, sessionID, signal) {
  const row = await core.cli(['wake', 'status', target.project, target.home], signal)
  if (!row.configured || row.runtime !== 'opencode' || row.native_session_id !== sessionID ||
      typeof row.stop_present !== 'boolean' || !row.stop_file) {
    throw new Error('PAOE Contact does not bind OpenCode session ' + sessionID + ' to ' + target.home)
  }
  return row
}

async function observe(core, target, event) {
  const { data_root } = await core.descriptor()
  const directory = join(data_root, 'runtime', 'opencode-context', target.home)
  await mkdir(directory, { recursive: true })
  await appendFile(join(directory, 'events.jsonl'), JSON.stringify({ at: new Date().toISOString(), ...event }) + '\n')
}

async function readFrame(core, state, signal) {
  const reason = state.reason ?? 'request'
  const { target } = state
  const sources = target.requiredSources ?? []
  const phase = sources.length ? await core.cli([
    'context', 'read', target.home, '--reason', reason,
    ...(core.config.catUrl ? ['--cat-url', core.config.catUrl] : []),
    ...sources.flatMap(source => ['--source', source]),
  ], signal) : await core.phase(target, reason, signal)
  if (phase.schema !== 'paoe-context/v1' || phase.home_id !== target.home || !phase.documents?.length) {
    throw new Error('PAOE returned no verified originals for ' + target.home)
  }
  const locals = phase.documents.filter(doc => doc.kind !== 'active_role')
  const roles = phase.documents.filter(doc => doc.kind === 'active_role')
  const text = phase.documents.map(doc => '## ' + doc.kind + ' · ' + doc.path + '\n' + doc.body).join('\n\n')
  return { task: phase.task_id, locals, roles, text }
}

async function install(ctx, options) {
  const core = new PaosCore(options)
  const selected = new Map()
  for (const [sessionID, target] of Object.entries(options.sessions ?? {})) {
    if (!sessionID.startsWith('ses_') || !target.project || !/^S\d{3}$/.test(target.home)) {
      throw new Error('Each selected OpenCode session needs an existing PAOE project and Home')
    }
    selected.set(sessionID, { target, reason: 'resume' })
  }
  if (!selected.size) throw new Error('No OpenCode sessions selected for PAOE')

  const lifetime = new AbortController()
  const { signal } = lifetime
  const write = (state, sessionID, action, details = {}) =>
    observe(core, state.target, { session: sessionID, action, ...details })
  const bindings = []
  bindings.push(await ctx.session.hook('context', async request => {
    const { sessionID } = request
    const state = selected.get(sessionID)
    if (!state) return
    state.ending?.abort()
    state.primary = false
    state.engaged = false
    const input = request.messages.findLast(message => message.role === 'user')
    const freshInput = state.inputID !== input?.id
    state.inputID = input?.id
    if (freshInput) state.automatic = input?.id ? await ctx.storage.get('continuation:' + sessionID + ':' + input.id) : undefined
    const automatic = state.automatic
    if (freshInput || !state.binding || state.reason) {
      state.binding = await contact(core, state.target, sessionID, signal)
    }
    state.engaged = true
    if (await core.stopped(state.binding.stop_file)) {
      if (automatic) throw new Error('PAOE STOP prevents an automatic continuation')
      return
    }
    try {
      if (state.reason || !state.frame || await changed(core, state, signal)) {
        state.frame = await readFrame(core, state, signal)
        state.reason = undefined
      }
    } catch (error) {
      state.frame = undefined
      await write(state, sessionID, 'originals_unavailable', { missing: error.missing ?? [], reason: error.message })
      throw error
    }
    if (automatic && (automatic.task !== state.frame.task || await core.stopped(state.binding.stop_file))) {
      throw new Error('PAOE task or STOP changed before automatic continuation')
    }

    const part = { type: 'text', text: state.frame.text }
    request.system.push(part)
    if (!request.system.includes(part) || (input && !request.messages.includes(input))) {
      throw new Error('OpenCode context is missing the PAOE originals or native input')
    }
    await write(state, sessionID, 'request_checked', {
      checkpoint: 'OpenCode context', task: state.frame.task, input: input?.id,
      versions: [...state.frame.locals, ...state.frame.roles].map(({kind, path, version}) => ({kind, path, version})),
    })
    state.primary = true
  }))

  bindings.push(await ctx.session.hook('compaction', request => {
    const state = selected.get(request.sessionID)
    if (state) state.reason = 'compact'
  }))

  const listen = async () => {
    for await (const { type, data } of ctx.event.subscribe({ signal, types: eventTypes })) {
      if (!eventTypes.includes(type)) continue
      const state = selected.get(data.sessionID)
      if (!state) continue
      if (type === interrupted) state.epoch = (state.epoch ?? 0) + 1
      if (type === 'session.compaction.ended') {
        state.reason = 'compact'
      } else if (type === 'session.compaction.started') {
        state.compactedInput = state.inputID
      } else if (type === started) {
        state.ending?.abort()
      } else if (state.engaged) {
        const { sessionID } = data
        const turn = {
          input: state.inputID, task: state.frame?.task, epoch: state.epoch,
          checked: state.primary, reentry: state.automatic?.id === state.inputID,
          outcome: type.slice('session.execution.'.length),
        }
        state.engaged = false
        // Do not wait from the context hook or block the stream observing interruptions.
        void endTurn(ctx, core, state, sessionID, turn, signal, write, data.error).catch(error => {
          if (!signal.aborted) console.error('PAOE OpenCode:', error.message)
        })
      }
    }
  }
  void listen().catch(error => {
    if (!signal.aborted) console.error('PAOE OpenCode events:', error.message)
  })
  return () => {
    lifetime.abort()
    for (const binding of bindings) binding.dispose()
  }
}

async function changed(core, state, signal) {
  for (const doc of state.frame.locals) {
    try {
      if (await core.currentVersion(doc.path) !== doc.version) return true
    } catch (error) {
      if (error.code === 'ENOENT') return true
      throw error
    }
  }
  return state.frame.roles.length > 0 && core.rolesChanged(state.frame.roles, state.target, signal)
}

function current(state, turn, signal) {
  return !signal.aborted && state.inputID === turn.input && state.epoch === turn.epoch
}

async function endTurn(ctx, core, state, sessionID, turn, lifetime, write, error) {
  const ending = new AbortController()
  state.ending = ending
  // A new native execution can begin while Core is reading CAT before writing presence.
  const signal = AbortSignal.any([lifetime, ending.signal])
  try {
    await settle(ctx, core, state, sessionID, turn, signal)
  } catch (error) {
    if (!signal.aborted || error.name !== 'AbortError') throw error
  } finally {
    if (state.ending === ending) state.ending = undefined
  }
  if (current(state, turn, signal) && turn.outcome === 'failed' && turn.checked && capacityRefusal(error)) {
    // Recovery starts a separate, deliberate native compaction execution.
    await recover(ctx, core, state, sessionID, turn, lifetime, write)
  }
}

async function settle(ctx, core, state, sessionID, turn, signal) {
  const { task, input } = turn
  if (!input) return
  await ctx.session.wait({ sessionID })
  if (!current(state, turn, signal)) return
  const binding = await contact(core, state.target, sessionID, signal)
  const stopped = binding.stop_present || await core.stopped(binding.stop_file)
  const presenceOnly = stopped || !task || !turn.checked || turn.outcome === 'failed'
  if (presenceOnly && !core.config.catUrl) return
  // The context snapshot also detects a newer execution before the event consumer sees it.
  const history = await ctx.session.context({ sessionID })
  const terminal = history.at(-1)
  if (!current(state, turn, signal) || history.findLast(message => message.type === 'user')?.id !== input ||
      terminal?.type !== 'idle' || terminal.outcome !== turn.outcome) return
  const flags = turn.outcome === 'interrupted' ? ['--interrupted']
    : presenceOnly ? ['--presence-only'] : turn.reentry ? ['--reentry'] : []
  const decision = await core.stop(state.target, id + ':' + sessionID + ':' + input, task, flags, signal)
  if (flags.length || decision.action !== 'continue' || !current(state, turn, signal) ||
      await core.stopped(binding.stop_file)) return
  await proceed(ctx, core, binding.stop_file, sessionID, task, decision.next_action, signal)
}

function capacityRefusal(error) {
  if (error?.type === 'context.overflow') return true
  if (error?.type !== 'provider.invalid-request' || typeof error.response?.body !== 'string') return false
  try { return JSON.parse(error.response.body)?.error?.code === 'context_length_exceeded' }
  catch (error) { if (error instanceof SyntaxError) return false; throw error }
}

async function recover(ctx, core, state, sessionID, turn, signal, write) {
  const { input, task } = turn
  const key = ['capacity', sessionID, task].join(':')
  if (state.target.recoverCapacity !== true) {
    await write(state, sessionID, 'capacity_owner', { task, input, reason: 'recovery_not_enabled' })
    return
  }
  if (!input || !task || state.automatic || state.compactedInput === input ||
      state.recovering || await ctx.storage.get(key)) {
    await write(state, sessionID, 'capacity_owner', { task, input, reason: 'already_attempted_or_not_current' })
    return
  }
  state.recovering = true
  try {
    await ctx.session.wait({ sessionID })
    if (!current(state, turn, signal)) return
    const binding = await contact(core, state.target, sessionID, signal)
    const before = await ctx.session.context({ sessionID })
    if (!current(state, turn, signal) || binding.stop_present || await core.stopped(binding.stop_file) ||
        before.findLast(message => message.type === 'user')?.id !== input ||
        !capacityRefusal(before.at(-1)?.error) || !before.some(message => message.type === 'assistant')) {
      await write(state, sessionID, 'capacity_owner', { task, input, reason: 'stopped_or_no_compactable_history' })
      return
    }
    const frame = await readFrame(core, state, signal)
    if (frame.task !== task || !current(state, turn, signal) || await core.stopped(binding.stop_file)) return
    await ctx.storage.set(key, { input })
    signal.throwIfAborted()
    if (!current(state, turn, signal) || await core.stopped(binding.stop_file)) return
    await write(state, sessionID, 'capacity_refused', { task, input, checkpoint: 'OpenCode provider response' })
    if (!current(state, turn, signal) || await core.stopped(binding.stop_file)) return
    const receipt = await ctx.session.compact({ sessionID })
    await write(state, sessionID, 'compaction_admitted', { task, input, compaction: receipt.id })
    await ctx.session.wait({ sessionID })
    if (!current(state, turn, signal)) return
    const after = await ctx.session.context({ sessionID })
    const compactIndex = after.findIndex(message => message.id === receipt.id &&
      message.type === 'compaction' && message.status === 'completed')
    if (compactIndex < 0) {
      await write(state, sessionID, 'capacity_owner', { task, input, reason: 'compaction_unconfirmed' })
      return
    }
    if (await core.stopped(binding.stop_file)) {
      await write(state, sessionID, 'capacity_owner', { task, input, reason: 'stopped_after_compaction' })
      return
    }
    if (!current(state, turn, signal) || after.slice(compactIndex + 1).some(message => message.type === 'user')) return
    state.reason = 'compact'
    state.frame = await readFrame(core, state, signal)
    if (state.frame.task !== task || !current(state, turn, signal) || await core.stopped(binding.stop_file)) return
    await write(state, sessionID, 'compaction_completed', { task, input, compaction: receipt.id })
    if (!current(state, turn, signal) || await core.stopped(binding.stop_file)) return
    await proceed(ctx, core, binding.stop_file, sessionID, task, '原生压缩完成。请读取当前工位原件，接续 ' + task + '。', signal)
  } finally {
    state.recovering = false
  }
}

async function proceed(ctx, core, stopFile, sessionID, task, text, signal) {
  const id = 'msg_' + globalThis.crypto.randomUUID().replaceAll('-', '')
  await ctx.storage.set('continuation:' + sessionID + ':' + id, { id, task })
  signal.throwIfAborted()
  if (await core.stopped(stopFile)) return
  await ctx.session.prompt({ sessionID, id, text, delivery: 'queue' })
}

export default { id, setup: ctx => install(ctx, ctx.options) }
