import type { AgentSummary } from '../types'

const STATUS_LABELS: Record<string, string> = {
  active: '在岗',
  paused: '暂停',
  standby: '待机',
  reserved: '保留',
  retired: '已退出',
  missing: '资料未补齐',
}

export function statusLabel(agent: AgentSummary): string {
  if (agent.ok === false) return '工位不可读'
  if (agent.registered === false) return '尚未接入'
  const raw = (agent.member_status || '').toLowerCase()
  if (raw && STATUS_LABELS[raw]) return STATUS_LABELS[raw]
  if (raw) return agent.member_status as string
  return '状态未标注'
}

export function displayNumber(agent: AgentSummary): string {
  return agent.number || agent.id
}

export function displayName(agent: AgentSummary): string {
  if (agent.name && agent.name !== agent.id) return agent.name
  return agent.id
}

export function displayRole(agent: AgentSummary): string {
  return agent.role || (agent.registered === false ? '资料未补齐' : '职责未标注')
}

export function isPaused(agent: AgentSummary): boolean {
  const raw = (agent.member_status || '').toLowerCase()
  return raw === 'paused' || raw === 'retired' || agent.can_contact === false
}

export function canStartCollaboration(agent: AgentSummary): boolean {
  return agent.ok !== false && agent.registered !== false && agent.can_contact !== false && !isPaused(agent)
}

export function actionText(agent: AgentSummary): string {
  if (agent.ok === false) return '无法读取工位，请检查路径或权限'
  if (isPaused(agent)) return '该成员当前暂停，旧 TODO 不代表可执行任务'
  return agent.next_action || agent.objective || '暂无当前行动'
}
