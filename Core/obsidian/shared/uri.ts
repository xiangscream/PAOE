export const CAT_PROTOCOL = 'paos-cat'

export function buildCatUri(vaultId: string, roomId: string): string {
  const params = new URLSearchParams({ room: roomId })
  if (vaultId) params.set('vault', vaultId)
  return `obsidian://${CAT_PROTOCOL}?${params.toString()}`
}

export function catRoomFromParams(params: Record<string, string>, currentVault: string, aliases: string[] = []): { room: string; error?: string } {
  const room = String(params.room || '').trim()
  if (!room) return { room: '', error: '缺少房间 ID，未打开 CAT。' }
  const vault = String(params.vault || '').trim()
  const allowed = new Set([currentVault, ...aliases].filter(Boolean))
  if (vault && !allowed.has(vault)) {
    return { room: '', error: `请求的 System 库是 ${vault}，当前库是 ${currentVault}。` }
  }
  return { room }
}
