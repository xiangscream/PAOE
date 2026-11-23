import { isDeepStrictEqual } from 'node:util'

function originalFrame(phase, target, create) {
  const versions = phase.documents.map(doc => doc.kind === 'active_role'
    ? { kind: doc.kind, path: doc.path, version: doc.version, plan: doc.plan_version, approval: doc.roles_receipt }
    : { kind: doc.kind, path: doc.path, version: doc.version })
  const text = phase.documents.map(doc => '## ' + doc.kind + ' · ' + doc.path + '\n' + doc.body).join('\n\n')
  return create({
    source: { kind: 'paoe-context', form: 'instructions', home: target.home, task: phase.task_id, versions },
    content: [{ type: 'text', text }],
  })
}

function sameFrame(message, frame) {
  return message?.role === 'user' && message.source?.kind === 'paoe-context' &&
    isDeepStrictEqual(message.source, frame.source) && isDeepStrictEqual(message.content, frame.content)
}

function hasInput(messages, original) {
  return messages.some(item => item.role === 'user' &&
    (item.id === original.id || (item.source?.kind === 'paoe-original-input' && item.source.originalId === original.id)) &&
    isDeepStrictEqual(item.content, original.content))
}

export function registerContextHooks(ctx, sessions, core, { createUserMessage, isAgentLoopRequest }) {
  const states = new Map()
  for (const target of Object.values(sessions)) {
    if (!target.project || !/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(target.home ?? '')) {
      throw new Error('Each selected DSH session needs its registered PAOE project and Home')
    }
  }
  ctx.effect(() => () => {
    for (const state of states.values()) state.recovery?.abort()
    states.clear()
  })

  function stateFor(agent) {
    const id = agent.session.id
    if (!Object.hasOwn(sessions, id)) return null
    let state = states.get(id)
    if (state?.agent !== agent) {
      state?.recovery?.abort()
      state = { agent, target: sessions[id], reason: 'resume', inputs: [], recoveries: 0, turn: 0, step: 0 }
      states.set(id, state)
    }
    return state
  }

  async function observe(s, action, detail = {}) {
    try {
      await core.observe(s.target, { session: s.agent.session.id, turn: s.turn, step: s.step, action,
        task: s.frame?.source.task ?? '', ...detail })
    } catch (error) {
      ctx.logger.warn('PAOE could not record %s: %s', action, error.message)
    }
  }

  async function reload(s, reason, signal) {
    s.blocked = true
    let phase
    try {
      phase = await core.phase(s.target, reason, signal)
    } catch (error) {
      s.frame = undefined
      s.reason = reason
      await observe(s, 'originals_unavailable', { reason, missing: error.missing ?? [] })
      throw error
    }
    const current = phase.documents.find(doc => doc.kind === 'current')
    if (!current) throw new Error('PAOE did not return the current Home TODO')
    const frame = originalFrame(phase, s.target, createUserMessage)
    const same = sameFrame(s.frame, frame)
    if (!same) s.frame = frame
    s.current = current
    s.roles = phase.documents.filter(doc => doc.kind === 'active_role')
    s.reason = undefined
    if (!same || reason !== 'request') await observe(s, 'originals_read', { reason, versions: s.frame.source.versions })
  }

  ctx.on('agent/created', ({ agent, source }) => {
    const s = stateFor(agent)
    if (s) s.reason = source === 'clear' ? 'startup' : source
  })
  ctx.on('agent/disposed', ({ agent }) => {
    const s = states.get(agent.session.id)
    if (s?.agent === agent) {
      s.recovery?.abort()
      states.delete(agent.session.id)
    }
  })

  ctx.on('agent/pre-step', async ({ agent, messages, turn, step, signal }, next) => {
    const decision = await next()
    const s = stateFor(agent)
    if (!s || decision.kind !== 'enter' || (step === 1 && decision.messages.length === 0)) return decision
    signal.throwIfAborted()
    const newTurn = s.turn !== turn
    if (newTurn || !s.contact || s.reason) s.contact = await core.contact(s.target, agent.session.id, signal)
    s.turn = turn
    s.step = step
    s.muted = s.contact.stopped || await core.stopped(s.contact.stopFile)
    if (s.muted) {
      const automatic = m => ['paoe-continuation', 'paoe-recovery'].includes(m.source?.kind)
      if (messages.length && messages.every(automatic)) return { ...decision, messages: [] }
      return decision.messages.some(automatic)
        ? { ...decision, messages: decision.messages.filter(m => !automatic(m)) } : decision
    }
    const direct = messages.filter(message => message.source?.kind === 'user')
    const fresh = direct.filter(message => !s.inputs.some(previous => previous.id === message.id))
    if (fresh.length) {
      s.inputs = newTurn ? direct : [...s.inputs, ...fresh]
      s.pending = undefined
      s.recovery?.abort()
      s.recoveries = 0
    }
    const changed = s.current && await core.currentVersion(s.current.path) !== s.current.version
    if (s.reason || !s.frame || changed || fresh.length || (s.roles.length && await core.rolesChanged(s.roles, s.target, signal))) {
      // Only a new boundary or changed working facts reload the full project and background originals.
      await reload(s, s.reason || 'request', signal)
    }
    signal.throwIfAborted()
    const history = [...agent.session.deriveMessages(), ...decision.messages]
    const additions = []
    const last = history.findLast(message => message.source?.kind === 'paoe-context' && message.source.home === s.target.home)
    if (!sameFrame(last, s.frame)) additions.push(s.frame)
    for (const input of s.inputs) {
      if (!hasInput(history, input)) {
        additions.push(createUserMessage({ source: { kind: 'paoe-original-input', form: 'instructions', originalId: input.id },
          content: input.content }))
      }
    }
    return additions.length ? { ...decision, messages: [...decision.messages, ...additions] } : decision
  })

  ctx.on('llm/stream', async function* (request, next) {
    if (!Object.hasOwn(sessions, request.sessionId ?? '')) { yield* next(); return }
    const s = states.get(request.sessionId)
    if (!s) throw new Error('PAOE has not restored the configured DSH session')
    if (!isAgentLoopRequest(request)) {
      if (request.purpose === 'compaction') {
        await observe(s, 'native_compaction_request')
      } else if (!request.purpose) {
        throw new Error('Unmarked DSH session request: check the AgentLoop SDK used by this installation')
      } else if (s.blocked) {
        throw new Error('Current PAOE task is blocked; read its originals or use native compaction')
      }
      yield* next()
      return
    }
    if (s.muted) { yield* next(); return }
    if (!s.frame || await core.stopped(s.contact.stopFile)) throw new Error('PAOE step is no longer active')
    // DSH deep-freezes this exact loop request before dispatch. Read it without rewriting it.
    const frame = request.messages.findLast(message => message.source?.kind === 'paoe-context' && message.source.home === s.target.home)
    const missing = s.inputs.filter(message => !hasInput(request.messages, message)).map(message => message.id)
    if (!sameFrame(frame, s.frame) || missing.length) {
      s.blocked = true
      await observe(s, 'request_missing_originals', { checkpoint: 'DSH llm/stream', missingInputIds: missing,
        framePresent: sameFrame(frame, s.frame) })
      throw new Error('DSH request lacks current PAOE originals for ' + s.target.home)
    }
    const model = await ctx.llm.resolveModelInfo(request.provider, request.model, request.signal)
    const window = model.context?.contextWindow
    const pressure = ctx.tokenMeter.measure(s.agent.session)
    const reserve = request.maxTokens ?? model.defaultMaxTokens ?? 0
    const available = window > 0 ? window - reserve : undefined
    const basis = { checkpoint: 'DSH llm/stream', frameId: frame.id, inputIds: s.inputs.map(m => m.id),
      versions: frame.source.versions, model: request.model, provider: request.provider,
      inputTokens: pressure.totalTokens, outputReserve: reserve, contextWindow: window ?? null }
    if (available !== undefined && pressure.totalTokens > available) {
      s.blocked = true
      const required = new Set([frame.id, ...s.inputs.map(m => m.id)])
      const visible = s.agent.session.deriveMessages()
      const selectedTokens = visible.length === pressure.nodes.length
        ? visible.reduce((sum, m, i) => required.has(m.id) || required.has(m.source?.originalId) ? sum + pressure.nodes[i].tokens : sum, 0)
        : undefined
      const recoverable = Boolean(s.frame.source.task) && s.recoveries === 0 && !(selectedTokens > available)
      if (recoverable) {
        s.recoveries++
        s.pending = { task: s.frame.source.task, turn: s.turn }
      }
      await observe(s, 'capacity_refused', { ...basis, selectedTokens, recovery: recoverable ? 'after_idle' : 'owner' })
      throw new Error('DSH request exceeds capacity for ' + s.target.home + '; external recovery: ' + (recoverable ? 'after idle' : 'owner'))
    }
    s.blocked = false
    await observe(s, 'request_checked', basis)
    yield* next()
  })

  async function recover(s, pending, controller) {
    const { agent, target } = s, { signal } = controller
    if (agent.status !== 'idle' || s.turn !== pending.turn || signal.aborted) return
    const contact = await core.contact(target, agent.session.id, signal)
    if (contact.stopped || signal.aborted || agent.status !== 'idle' || s.turn !== pending.turn) return
    const result = await ctx.compaction.compactNow(agent, signal)
    if (!result) { await observe(s, 'no_compactable_history'); return }
    await reload(s, 'compact', signal)
    if (s.frame.source.task !== pending.task || signal.aborted || agent.status !== 'idle' ||
        s.turn !== pending.turn || await core.stopped(contact.stopFile)) return
    await observe(s, 'compaction_completed', { summarySeq: result.summarySeq })
    agent.followup(createUserMessage({ source: { kind: 'paoe-recovery', form: 'instructions' },
      content: [{ type: 'text', text: '原生压缩已完成，沿当前工位原件接续 ' + pending.task + '。' }] }))
  }

  ctx.on('agent/status', ({ agent, status }) => {
    const s = states.get(agent.session.id)
    if (!s?.pending || s.agent !== agent || status !== 'idle') return
    const pending = s.pending
    s.pending = undefined
    const controller = new AbortController()
    s.recovery = controller
    // Maintenance needs idle. Schedule outside both the rejected request and the transition callback.
    setImmediate(() => recover(s, pending, controller).catch(async error => {
      if (!controller.signal.aborted) {
        ctx.logger.warn('PAOE compaction failed for %s: %s', s.target.home, error.message)
        await observe(s, 'compaction_failed', { reason: error.name })
      }
    }))
  })

  ctx.on('agent/turn-stopping', async ({ agent, turn, signal }) => {
    const s = states.get(agent.session.id)
    if (!s?.frame || s.agent !== agent || s.blocked || s.muted || signal.aborted || await core.stopped(s.contact.stopFile)) return
    const flags = s.correctedTurn === turn ? ['--reentry'] : []
    const decision = await core.stop(s.target, 'dsh:' + agent.session.id + ':' + turn, s.frame.source.task, flags, signal)
    if (decision.action === 'continue' && !flags.length && !signal.aborted && !await core.stopped(s.contact.stopFile)) {
      s.correctedTurn = turn
      agent.steer(createUserMessage({ source: { kind: 'paoe-continuation', form: 'instructions' },
        content: [{ type: 'text', text: decision.next_action }] }))
    }
  })

  ctx.on('session/event', (session, event) => {
    const s = states.get(session.id)
    if (!s || s.agent.session !== session) return
    if (event.type === 'compaction/summary') s.reason = 'compact'
    if (event.type === 'turn/end' && ['aborted', 'interrupted'].includes(event.data.reason.kind)) {
      s.pending = undefined
      s.recovery?.abort()
      if (s.contact && !s.muted) {
        void core.stop(s.target, 'dsh:' + session.id + ':' + event.data.turn, s.frame?.source.task, ['--interrupted'])
          .catch(error => ctx.logger.warn('PAOE interrupt readback failed: %s', error.message))
      }
    }
  })
}
