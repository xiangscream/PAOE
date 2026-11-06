export interface AgentSummary {
  id: string
  ok?: boolean
  error?: string
  objective?: string
  next_action?: string
  tasks?: { doing?: number; total?: number; [key: string]: number | undefined }
  pending_notices?: number
  mail_total?: number
  number?: string
  name?: string
  role?: string
  member_status?: string
  registered?: boolean
  can_contact?: boolean
  team_path?: string
}

export interface ProjectOption {
  id: string
  name?: string
}

export interface LibraryItem {
  id: string
  kind: 'workflow' | 'skill' | 'tool'
  title?: string
  path?: string
  description?: string
}

export interface RoomSummary {
  id: string
  title?: string
  status?: string
  member_count?: number
  message_count?: number
  created_at?: string
}

export interface MemberView {
  home_id: string
  label?: string
  state?: string
}

export interface ChatMessage {
  id: string
  seq: number
  sender_id: string
  body: string
  reply_to?: string
  created_at: string
}

export interface Dashboard {
  ok: boolean
  project: string
  coordinator?: string
  agents: AgentSummary[]
  projects: ProjectOption[]
  index?: string
  examples: Record<string, LibraryItem[]>
  rooms?: RoomSummary[]
  cat?: { ok: boolean; error?: string; error_code?: string }
  team?: { path?: string; body?: string }
  error?: string
  error_code?: string
}

export interface AgentDetail extends AgentSummary {
  home_path?: string
  todo?: string
  entry?: string
  mails?: Array<{ name: string; preview: string }>
  docs?: string[]
  task_items?: unknown[]
  project?: string
}

export interface LayoutNode {
  x: number
  y: number
}

export interface BoardLayout {
  nodes: Record<string, LayoutNode>
  viewport: { x: number; y: number; zoom: number }
}

export interface LayoutResponse {
  ok: boolean
  project: string
  layout: BoardLayout
}

export interface ResourceResponse {
  ok: boolean
  resource: { id: string; kind: string; title?: string; path?: string; body?: string }
}

export interface DocumentResponse {
  ok: boolean
  path: string
  body: string
}

export type CollabMode = 'chat' | 'mail'
export type CollabState = 'saved' | 'failed' | 'unknown' | 'partial'
export type NotificationState = 'queued' | 'accepted' | 'partial' | 'not_requested' | 'unknown'

export interface CollabResult {
  ok?: boolean
  state?: CollabState
  mode?: CollabMode
  phase?: string
  message_id?: string
  room_id?: string
  notification?: NotificationState
  detail?: string
  error?: string
  error_code?: string
  result?: unknown
  status?: number
}

export interface RoomDetail {
  ok: boolean
  id?: string
  title?: string
  status?: string
  members?: MemberView[]
  messages?: ChatMessage[]
  error?: string
  error_code?: string
}
