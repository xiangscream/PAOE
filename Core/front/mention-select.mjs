// CAT 任务房首片：选人与收件范围预览的共用纯逻辑。
// 规则来源：Decisions/20261120-CAT任务房与在线协作设计.md 与 Works/CAT-TASKROOM-20261120/CONTRACT.md。
// 边界：候选只来自成员/员工事实；收件范围只认后台 preview 的返回，不解析正文 @；
// unknown 不当 offline 展示，也不给「将唤醒」提示。
const PRESENCE_LABELS = { online: '在线', offline: '离线', unknown: '状态未知' };
const ORDER = { online: 0, unknown: 1, offline: 2 };

export function presenceInfo(presence) {
  const value = presence === 'online' || presence === 'offline' ? presence : 'unknown';
  return { value, label: PRESENCE_LABELS[value], wakeHint: value === 'offline' ? '将唤醒' : '' };
}

export function staffId(person) {
  return person?.staff_number || person?.number || person?.home_id || person?.id || '';
}

export function roleLine(person, member) {
  const roles = Array.isArray(person?.roles) && person.roles.length ? person.roles.join(' · ')
    : (typeof person?.role === 'string' && person.role ? person.role : '');
  return roles || member?.label || '';
}

// 房内可点名候选：participant 且非 human；在线在前、状态未知次之、离线最后，组内按工号稳定排序。
export function memberCandidates(members, query = '') {
  const needle = query.trim().toLowerCase();
  return (members || [])
    .filter(member => member.state === 'participant' && member.home_id !== 'human')
    .map(member => ({ ...member, presence: presenceInfo(member.presence).value }))
    .filter(member => !needle
      || member.home_id.toLowerCase().includes(needle)
      || (member.label || '').toLowerCase().includes(needle))
    .sort((a, b) => ORDER[a.presence] - ORDER[b.presence] || a.home_id.localeCompare(b.home_id));
}

// 房外候选：只在有搜索词时给出；排除已在房内者，按员工号/称呼匹配。
export function outsideCandidates(people, members, query = '') {
  const needle = query.trim().toLowerCase();
  if (!needle) return [];
  const seated = new Set((members || []).map(member => member.home_id));
  return (people || []).filter(person => {
    const id = staffId(person);
    if (!id || id === 'human' || seated.has(id) || (person.home_id && seated.has(person.home_id))) return false;
    return id.toLowerCase().includes(needle)
      || (person.name || '').toLowerCase().includes(needle)
      || roleLine(person).toLowerCase().includes(needle);
  });
}

// 收件范围文案：只复述 preview 的事实；后端未就绪时如实说明，不自行推断。
export function scopeText(preview) {
  if (!preview) return '';
  if (preview.unavailable) return '收件预览暂不可用';
  if (preview.recipient_mode === 'all')
    return `提醒全房 · ${Array.isArray(preview.recipients) ? preview.recipients.length : 0} 位成员`;
  if (preview.recipient_mode === 'selected')
    return `点名提醒 ${Array.isArray(preview.recipients) ? preview.recipients.length : 0} 人`;
  if (preview.recipient_mode === 'none') return '普通发言 · 静默';
  return '';
}

// 名册口径（Rooter 补充 / CONTRACT.md §1）：observer 是明确退出执行与提醒范围的只读旁听，
// 必须显示「旁听，不在任务组」，不得当成离线任务成员或暗中缩小提醒范围；left 已退席。
export function rosterEntry(member) {
  if (member?.state === 'observer') return {kind:'observer', presenceLabel:'旁听，不在任务组', detail:'已明确退出执行与提醒范围', wakeHint:''};
  if (member?.state === 'left') return {kind:'left', presenceLabel:'已退席', detail:'', wakeHint:''};
  const info = presenceInfo(member?.presence);
  return {kind:'participant', presenceLabel:info.label, detail:'', wakeHint:info.wakeHint};
}

export function observerNote(members) {
  const count = (members || []).filter(member => member.state === 'observer').length;
  return count ? `另有 ${count} 位旁听不在提醒范围` : '';
}

