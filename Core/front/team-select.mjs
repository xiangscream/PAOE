// PAOE 0.1 任务房前端共用纯逻辑：团队计划卡、角色卡与两次放行状态。
// 合同来源：msg-s010-s040-paoe01-team-ui-20261123 ①②③、msg-s010-s040-paoe01-team-names-20261123、
// msg-s010-s040-team-approval-labels-20261123 与 paired-smoke.py 实际 API 形状。
// 前端只展示；批准/放行/验收的状态判定全在后台（GET /api/rooms/R/team 与 task accept CLI），
// 本模块不做第二套推断。四步：open-plan 通过计划并建房（第一次）→ approve-roles 放行角色（第二次）
// → save-role 调整角色 → task accept 为 Human 保留的最终验收。

const RELEASE_STAGES = { pending: '计划待确认', opened: '已建房·角色收集中', released: '角色已放行', accepted: '已验收·房可关闭' };

// 角色卡状态：approved=false 是草案，true 是 Human 放行后的正式角色。
export function roleCardState(roleEntry) {
  if (!roleEntry || !roleEntry.role) return { kind: 'empty', label: '未提交', hint: '成员尚未提交角色草案', revision: roleEntry?.revision || 0 };
  const { approved, revision } = roleEntry;
  if (approved === true) return { kind: 'approved', label: RELEASE_STAGES.released, hint: 'Human 已放行，可接入执行 Task', revision: revision || 0 };
  return { kind: 'draft', label: '草案', hint: '等待 Human 放行', revision: revision || 0 };
}

// 团队整体阶段：以全部成员卡与 accepted 标志描述当前位置。不替后台判断。
export function teamStage(team) {
  if (!team) return { label: '', hint: '', tone: '' };
  if (team.accepted === true || team.owner_acceptance) return { label: RELEASE_STAGES.accepted, hint: '目标已验收，专用房可关闭', tone: 'accepted' };
  const entries = Object.values(team.roles || {});
  const states = entries.map(roleCardState);
  if (states.length && states.every(s => s.kind === 'approved'))
    return { label: RELEASE_STAGES.released, hint: '角色已放行，成员可接入执行 Task', tone: 'released' };
  if (states.some(s => s.kind === 'draft'))
    return { label: RELEASE_STAGES.opened, hint: '有草案待 Human 放行（第二次放行）', tone: 'draft' };
  return { label: RELEASE_STAGES.opened, hint: '等待成员提交角色卡', tone: 'draft' };
}

// 计划卡摘要行：project · owner · version · close_policy · members
export function planSummary(plan) {
  if (!plan) return '';
  const parts = [];
  if (plan.project) parts.push('项目 ' + plan.project);
  if (plan.owner) parts.push('负责人 ' + plan.owner);
  if (plan.version) parts.push('v' + plan.version);
  if (plan.close_policy === 'human_confirm') parts.push('关房需 Human 确认');
  else if (plan.close_policy === 'owner') parts.push('负责人可关');
  const members = plan.members || [];
  if (members.length) parts.push(members.length + ' 名成员');
  return parts.join(' · ');
}

export function planMembers(plan) {
  return (plan?.members || []).filter(id => typeof id === 'string' && id.length);
}

// 两次放行的实际操作标签（合同修正后：open-plan 是第一次，approve-roles 是第二次）
export const HUMAN_ACTIONS = {
  'open-plan': { label: '通过计划并建房', hint: '第一次放行：Human 确认准确计划后创建专用房', order: 1 },
  'approve-roles': { label: '放行角色卡', hint: '第二次放行：确认角色分工，成员可接入执行 Task', order: 2 },
  'save-role': { label: '调整角色', hint: '修改本人角色草案（不触发放行）', order: 0 },
  'task-accept': { label: '验收目标', hint: 'Human 保留的最终验收：确认目标完成，专用房可关闭', order: 3 },
};

// 角色卡显示行：duty · arrangement · deliverables
export function roleLine(role) {
  if (!role) return '';
  return [role.duty, role.arrangement, role.deliverables].filter(Boolean).join(' · ');
}
