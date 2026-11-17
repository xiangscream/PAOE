export interface TransportResponse {
  ok: boolean
  status: number
  json(): Promise<any>
}

export type ApiTransport = (url: string, init?: RequestInit) => Promise<TransportResponse>

let activeTransport: ApiTransport | null = null

export function setApiTransport(transport: ApiTransport | null): void {
  activeTransport = transport
}

export async function requestTransport(url: string, init?: RequestInit): Promise<TransportResponse> {
  if (activeTransport) return activeTransport(url, init)
  return fetch(url, { cache: 'no-store', ...init })
}
