import { spawn } from 'child_process'

export interface BridgeConfig {
  pythonPath: string
  installationFile: string
  bridgePath: string
  vaultRoot: string
  catUrl?: string
}

export interface BridgeRequest {
  method: string
  path: string
  body?: unknown
}

export interface BridgeResponse {
  status: number
  body: any
}

export type BridgeRunner = (config: BridgeConfig, request: BridgeRequest) => Promise<BridgeResponse>

function errorResponse(error: unknown, code = 'bridge_failed'): BridgeResponse {
  const message = error instanceof Error ? error.message : String(error)
  return { status: 0, body: { ok: false, error_code: code, error: message } }
}

export const runBridge: BridgeRunner = (config, request) => new Promise(resolve => {
  let settled = false
  let stdout = ''
  let stderr = ''
  const finish = (response: BridgeResponse) => {
    if (settled) return
    settled = true
    clearTimeout(timer)
    resolve(response)
  }
  const timer = setTimeout(() => finish(errorResponse('PAOS 桥请求超时（45 秒）', 'bridge_timeout')), 45000)
  try {
    const child = spawn(config.pythonPath, [
      config.bridgePath,
      '--installation-file', config.installationFile,
      '--vault-root', config.vaultRoot,
      ...(config.catUrl ? ['--cat-url', config.catUrl] : []),
    ], { windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] })
    child.stdout?.on('data', (chunk: any) => { stdout += String(chunk) })
    child.stderr?.on('data', (chunk: any) => { stderr += String(chunk) })
    child.on('error', (error: any) => finish(errorResponse(error, 'bridge_unavailable')))
    child.on('close', (code: any) => {
      if (settled) return
      const line = stdout.trim().split(/\r?\n/).reverse().find(item => item.trim().startsWith('{'))
      if (!line) {
        finish(errorResponse(stderr || `PAOS 桥退出，状态码 ${code}`, 'bridge_invalid_output'))
        return
      }
      try {
        const parsed = JSON.parse(line)
        if (!parsed || typeof parsed.status !== 'number' || typeof parsed.body !== 'object') {
          finish(errorResponse('PAOS 桥响应缺少 status/body', 'bridge_invalid_output'))
          return
        }
        finish({ status: parsed.status, body: parsed.body })
      } catch (error) {
        finish(errorResponse(error, 'bridge_invalid_output'))
      }
    })
    child.stdin?.end(JSON.stringify(request))
  } catch (error) {
    finish(errorResponse(error, 'bridge_unavailable'))
  }
})

export function bridgeTransport(config: BridgeConfig, runner: BridgeRunner = runBridge) {
  return async (url: string, init: RequestInit = {}) => {
    let body: unknown
    if (typeof init.body === 'string' && init.body) {
      try { body = JSON.parse(init.body) } catch { body = init.body }
    }
    const response = await runner(config, {
      method: init.method || 'GET',
      path: url,
      ...(body !== undefined ? { body } : {}),
    })
    return {
      ok: response.status >= 200 && response.status < 300 && response.body?.ok !== false,
      status: response.status,
      json: async () => response.body,
    }
  }
}
