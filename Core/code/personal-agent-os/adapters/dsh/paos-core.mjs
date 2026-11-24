import { spawn } from 'node:child_process'
import { appendFile, mkdir, readFile, stat } from 'node:fs/promises'
import { isAbsolute, join } from 'node:path'

// Invoke Python directly on Windows as well. All CLI parameters remain separate arguments.
function callPython(executable, args, signal) {
  return new Promise((resolve, reject) => {
    const child = spawn(executable, args, { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'], signal })
    const out = [], err = []
    child.stdout.on('data', part => out.push(part))
    child.stderr.on('data', part => err.push(part))
    child.once('error', reject)
    child.once('close', code => {
      try {
        const text = Buffer.concat(code === 0 ? out : (err.length ? err : out)).toString('utf8')
        const result = JSON.parse(text)
        if (!result.ok || code !== 0) {
          const missing = result.missing ?? result.context?.missing ?? []
          const problem = new Error(result.error || missing.map(x => x.path + ' (' + x.reason + ')').join(', ') || 'PAOE CLI failed')
          problem.missing = missing.map(({ kind, path, reason }) => ({ kind, path, reason }))
          throw problem
        }
        resolve(result)
      } catch (error) {
        reject(error)
      }
    })
  })
}

export class PaosCore {
  constructor(config) {
    if (!config.installation || !isAbsolute(config.installation)) throw new Error('PAOE installation descriptor required')
    this.config = config
  }

  async descriptor() {
    const data = JSON.parse((await readFile(this.config.installation, 'utf8')).replace(/^\uFEFF/, ''))
    if (data.schema !== 'paos-installation/v1' || !isAbsolute(data.source_root) || !isAbsolute(data.data_root)) {
      throw new Error('PAOE installation must identify its Source and Data roots')
    }
    return data
  }

  async cli(args, signal) {
    const { source_root } = await this.descriptor()
    return callPython(this.config.python ?? 'python', [
      '-X', 'utf8', '-B', join(source_root, 'scripts', 'paos.py'),
      '--installation-file', this.config.installation, '--json', ...args,
    ], signal)
  }

  async contact(target, sessionId, signal) {
    const row = await this.cli(['wake', 'status', target.project, target.home], signal)
    if (!row.configured || row.runtime !== 'dsh' || row.native_session_id !== sessionId) {
      throw new Error('PAOE Contact does not bind this DSH session to ' + target.home)
    }
    if (typeof row.stop_present !== 'boolean' || !row.stop_file) throw new Error('PAOE Contact has no verified STOP location')
    return { stopped: row.stop_present, stopFile: row.stop_file }
  }

  async stopped(path) {
    try { await stat(path); return true }
    catch (error) { if (error.code === 'ENOENT') return false; throw error }
  }

  async phase(target, reason, signal) {
    const cat = this.config.catUrl ? ['--cat-url', this.config.catUrl] : []
    const value = await this.cli(['context', 'read', target.home, '--reason', reason, ...cat], signal)
    if (value.schema !== 'paoe-context/v1' || value.home_id !== target.home || !value.documents?.length) {
      throw new Error('PAOE returned no verified originals for ' + target.home)
    }
    return value
  }

  async currentVersion(path) {
    const info = await stat(path, { bigint: true })
    return info.mtimeNs + ':' + info.size
  }

  async rolesChanged(roles, target, signal) {
    for (const role of roles) {
      const room = role.path.slice('cat-role:'.length)
      const url = new URL('/api/rooms/' + encodeURIComponent(room) + '/team', this.config.catUrl)
      const response = await fetch(url, { signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(5000)]) : AbortSignal.timeout(5000) })
      if (!response.ok) throw new Error('Cannot read CAT role in ' + room + ' (HTTP ' + response.status + ')')
      const { team } = await response.json(), own = team.roles[target.home]
      if (team.accepted || !own?.approved || String(own.revision) !== role.version ||
          team.plan.version !== role.plan_version || team.roles_receipt !== role.roles_receipt) return true
      const latest = await this.cli(['team-plan', 'plan', team.plan.owner, '--task', team.plan.task], signal)
      if (latest.plan.version !== role.plan_version) return true
    }
    return false
  }

  stop(target, event, task, flags, signal) {
    const cat = this.config.catUrl ? ['--cat-url', this.config.catUrl] : []
    return this.cli(['context', 'stop', target.home, '--event', event, ...(task ? ['--task', task] : []), ...flags, ...cat], signal)
  }

  async observe(target, record) {
    const { data_root } = await this.descriptor()
    const dir = join(data_root, 'runtime', 'dsh-context', target.home)
    await mkdir(dir, { recursive: true })
    await appendFile(join(dir, 'events.jsonl'), JSON.stringify({ at: new Date().toISOString(), ...record }) + '\n', 'utf8')
  }
}
