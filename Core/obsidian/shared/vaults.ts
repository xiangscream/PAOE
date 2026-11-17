import { existsSync, readFileSync } from 'fs'
import { homedir } from 'os'
import path from 'path'

function normalize(value: string): string {
  return value.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()
}

export function vaultAliases(vaultRoot: string): string[] {
  const candidates = [
    process.env.APPDATA ? path.join(process.env.APPDATA, 'obsidian', 'obsidian.json') : '',
    path.join(homedir(), 'AppData', 'Roaming', 'obsidian', 'obsidian.json'),
    path.join(homedir(), '.config', 'obsidian', 'obsidian.json'),
  ].filter(Boolean)
  for (const file of candidates) {
    if (!existsSync(file)) continue
    try {
      const parsed = JSON.parse(readFileSync(file, 'utf8'))
      const target = normalize(vaultRoot)
      const aliases: string[] = []
      for (const [id, info] of Object.entries(parsed?.vaults || {})) {
        const value = info as any
        if (normalize(String(value?.path || '')) === target) {
          aliases.push(id)
          if (value?.name) aliases.push(String(value.name))
        }
      }
      if (aliases.length) return aliases
    } catch {
      /* Obsidian config is optional; name still works. */
    }
  }
  return []
}
