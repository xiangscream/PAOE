import { createRequire } from 'node:module'
import { isAbsolute, join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { PaosCore } from './paos-core.mjs'
import { registerContextHooks } from './session.mjs'

export const inject = ['agents', 'llm', 'tokenMeter', 'compaction']

export async function apply(ctx, config = {}) {
  if (!Object.keys(config.sessions ?? {}).length) return
  const install = process.env.DSH_INSTALL_DIR
  const entry = install ? join(install, 'package.json') : process.argv[1]
  if (!entry || !isAbsolute(entry)) throw new Error('Cannot locate the running DSH launcher for the selected PAOE sessions')
  // Request ownership is a process-local WeakSet. Resolve the very SDK imported by this AgentLoop.
  const host = createRequire(entry)
  const loop = createRequire(host.resolve('@deepseek-ai/dsh-agent-loop'))
  const sdk = await import(pathToFileURL(loop.resolve('@deepseek-ai/dsh-llm')).href)
  registerContextHooks(ctx, config.sessions, new PaosCore(config), sdk)
}
