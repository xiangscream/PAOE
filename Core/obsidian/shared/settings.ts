import { existsSync, readFileSync } from 'fs'
import { homedir } from 'os'
import path from 'path'

export interface PaosBridgeSettings {
  pythonPath: string
  installationFile: string
  bridgePath: string
  catUrl: string
  systemVault: string
}

export const DEFAULT_SETTINGS: PaosBridgeSettings = {
  pythonPath: 'python',
  installationFile: '~/.paos/installation.json',
  bridgePath: '',
  catUrl: 'http://127.0.0.1:8870',
  systemVault: '',
}

export function expandHome(value: string): string {
  if (value === '~') return homedir()
  if (value.startsWith('~/') || value.startsWith('~\\')) return path.join(homedir(), value.slice(2))
  return value
}

export function normalizeSettings(value: Partial<PaosBridgeSettings> | null | undefined): PaosBridgeSettings {
  return {
    ...DEFAULT_SETTINGS,
    ...(value || {}),
    pythonPath: String(value?.pythonPath || DEFAULT_SETTINGS.pythonPath).trim() || DEFAULT_SETTINGS.pythonPath,
    installationFile: String(value?.installationFile || DEFAULT_SETTINGS.installationFile).trim() || DEFAULT_SETTINGS.installationFile,
    bridgePath: String(value?.bridgePath || '').trim(),
    catUrl: String(value?.catUrl || DEFAULT_SETTINGS.catUrl).trim(),
    systemVault: String(value?.systemVault || '').trim(),
  }
}

export interface ResolvedBridge {
  pythonPath: string
  installationFile: string
  bridgePath: string
  catUrl: string
  systemRoot: string
}

export function resolveBridge(settings: PaosBridgeSettings): ResolvedBridge {
  const installationFile = path.resolve(expandHome(settings.installationFile))
  if (!existsSync(installationFile)) throw new Error('安装描述不存在：' + installationFile)
  let installation: any
  try {
    installation = JSON.parse(readFileSync(installationFile, 'utf8'))
  } catch (error) {
    throw new Error('安装描述无法读取：' + String(error))
  }
  const sourceRoot = String(installation?.source_root || '').trim()
  if (!sourceRoot) throw new Error('安装描述缺少 source_root')
  const systemRoot = path.resolve(sourceRoot, '..', '..', '..')
  const bridgePath = settings.bridgePath
    ? path.resolve(expandHome(settings.bridgePath))
    : path.join(systemRoot, 'Core', 'front', 'paos_obsidian_bridge.py')
  if (!existsSync(bridgePath)) throw new Error('PAOS 桥不存在：' + bridgePath)
  return {
    pythonPath: expandHome(settings.pythonPath),
    installationFile,
    bridgePath,
    catUrl: settings.catUrl,
    systemRoot,
  }
}
