import type {
  AgentDetail,
  BoardLayout,
  CollabMode,
  CollabResult,
  Dashboard,
  DocumentResponse,
  LayoutResponse,
  LibraryItem,
  ResourceResponse,
  RoomDetail,
  RoomSummary,
} from './types'

export class ApiError extends Error {
  code: string
  status: number
  retry?: boolean

  constructor(message: string, code = 'request_failed', status = 0, retry?: boolean) {
    super(message)
    this.code = code
    this.status = status
    this.retry = retry
  }
}

function messageOf(value: any): string {
  if (typeof value?.error === 'string') return value.error
  if (typeof value?.error?.message === 'string') return value.error.message
  if (typeof value?.detail === 'string') return value.detail
  return value?.error_code || '请求未完成'
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, { cache: 'no-store', ...init })
  } catch {
    throw new ApiError('本地服务未连接', 'network_error', 0, true)
  }
  let data: any = null
  try {
    data = await response.json()
  } catch {
    throw new ApiError('服务返回了非 JSON 内容', 'invalid_response', response.status, true)
  }
  if (!response.ok || data?.ok === false) {
    throw new ApiError(messageOf(data), data?.error_code || 'request_failed', response.status, data?.retry)
  }
  return data as T
}

const projectQuery = (project: string) => '?project=' + encodeURIComponent(project)

async function receipt<T extends { status?: number }>(url: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, { cache: 'no-store', ...init })
  } catch {
    throw new ApiError('本地服务未连接', 'network_error', 0, true)
  }
  let data: any = null
  try {
    data = await response.json()
  } catch {
    throw new ApiError('服务返回了非 JSON 内容', 'invalid_response', response.status, true)
  }
  if (!data || typeof data !== 'object') throw new ApiError('服务回执为空', 'invalid_response', response.status, true)
  if (typeof data.status !== 'number') data.status = response.status
  return data as T
}

export const api = {
  dashboard(project: string) {
    return request<Dashboard>('/api/dashboard' + (project ? projectQuery(project) : ''))
  },
  agent(homeId: string) {
    return request<AgentDetail>('/api/agent/' + encodeURIComponent(homeId))
  },
  getLayout(project: string) {
    return request<LayoutResponse>('/api/layout' + projectQuery(project))
  },
  saveLayout(project: string, layout: BoardLayout) {
    return request<LayoutResponse>('/api/layout', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project, layout }),
    })
  },
  resource(kind: string, id: string) {
    return request<ResourceResponse>(
      '/api/library/resource?kind=' + encodeURIComponent(kind) + '&id=' + encodeURIComponent(id),
    )
  },
  document(project: string, path: string) {
    return request<DocumentResponse>(
      '/api/document?project=' + encodeURIComponent(project) + '&path=' + encodeURIComponent(path),
    )
  },
  collaborate(payload: {
    project: string
    mode: CollabMode
    members: string[]
    topic: string
    body: string
    message_id: string
    remind: boolean
    room_id?: string
  }) {
    return receipt<CollabResult>('/api/collaboration', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  collaborationFact(project: string, mode: CollabMode, messageId: string, roomId?: string) {
    const params = new URLSearchParams({ project, mode, message_id: messageId })
    if (roomId) params.set('room_id', roomId)
    return receipt<CollabResult>('/api/collaboration?' + params.toString())
  },
  rooms() {
    return request<{ ok: boolean; rooms: RoomSummary[] }>('/api/cat/rooms')
  },
  people() {
    return request<{ ok: boolean; people: Array<{ id: string; name?: string; number?: string; role?: string; project?: string }> }>(
      '/api/cat/people',
    )
  },
  room(id: string) {
    return request<RoomDetail>('/api/room/' + encodeURIComponent(id))
  },
  messages(id: string, after: number) {
    return request<{ ok: boolean; messages: RoomDetail['messages'] }>(
      '/api/room/' + encodeURIComponent(id) + '/messages?after=' + after,
    )
  },
  sendRoomMessage(id: string, body: string, messageId: string, replyTo = '') {
    return request<CollabResult>('/api/room/' + encodeURIComponent(id) + '/message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sender_id: 'human', body, message_id: messageId, reply_to: replyTo }),
    })
  },
  createRoom(title: string, members: string[]) {
    return request<{ ok: boolean; room_id?: string; error?: string; error_code?: string; status?: number }>('/api/room', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, members }),
    })
  },
  eventsUrl(roomId: string, after: number) {
    return '/api/room/' + encodeURIComponent(roomId) + '/events?after=' + after
  },
}

export type { LibraryItem }
