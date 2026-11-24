// PAOE 0.1 任务房前端共用纯逻辑：团队计划卡、角色卡、两次放行状态与 Human 操作入口。
// 合同来源：msg-s010-s040-paoe01-team-ui-20261123 ①②③、team-names、team-approval-labels、
// team-bridge-actions-real-entry-20261124 与 paired-smoke.py 实际 API 形状。
// 前端只展示与提交（POST /api/team/confirm {action, receipt_id, input}）；
// 批准/放行/验收的状态判定全在后台（GET /api/rooms/R/team），本模块不做第二套推断。
// 四步：open-plan 通过计划并建房（第一次放行）→ approve-roles 放行角色（第二次放行）
// → save-role 调整角色 → accept-goal 为 Human 保留的最终验收。

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
  // accepted 实为对象或 null（S010 配对复核确认），truthy 即已验收。
  if (team.accepted || team.owner_acceptance) return { label: RELEASE_STAGES.accepted, hint: '目标已验收，专用房可关闭', tone: 'accepted' };
  const entries = Object.values(team.roles || {});
  const states = entries.map(roleCardState);
  if (states.length && states.every(s => s.kind === 'approved'))
    return { label: RELEASE_STAGES.released, hint: '角色已放行，可接入执行 Task', tone: 'released' };
  if (states.some(s => s.kind === 'draft'))
    return { label: RELEASE_STAGES.opened, hint: '有草案待 Human 放行（第二次放行）', tone: 'draft' };
  return { label: RELEASE_STAGES.opened, hint: '等待成员提交角色卡', tone: 'draft' };
}

// 计划全部席位的角色卡：按计划 members 列出所有座位（含尚无草案的，初始 revision=0）。
export function allSeatRoles(team) {
  if (!team) return [];
  const roles = team.roles || {};
  const seats = planMembers(team.plan);
  return seats.map(home => {
    const entry = roles[home];
    if (entry) return { home, ...entry, state: roleCardState(entry) };
    return { home, role: null, approved: false, revision: 0, state: roleCardState(null) };
  });
}

// close_policy=human_confirm 时，owner 房不显示保留给 Human 的最终验收。
export function canShowAcceptGoal(team, viewerIsOwner) {
  if (!team || team.accepted || team.owner_acceptance) return false;
  if (team.plan?.close_policy === 'human_confirm' && viewerIsOwner) return false;
  const entries = Object.values(team.roles || {});
  return entries.length > 0 && entries.every(e => !e.role || e.approved === true);
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

// 两次放行的实际操作（合同修正后：open-plan 第一次，approve-roles 第二次；accept-goal 非 task-accept）
export const HUMAN_ACTIONS = {
  'open-plan': { label: '通过计划并建房', hint: '第一次放行：Human 确认准确计划后创建专用房', order: 1 },
  'approve-roles': { label: '放行角色卡', hint: '第二次放行：确认角色分工，成员可接入执行 Task', order: 2 },
  'save-role': { label: '调整角色', hint: '修改角色草案（不触发放行）', order: 0 },
  'accept-goal': { label: '验收目标', hint: 'Human 保留的最终验收：确认目标完成，专用房可关闭', order: 3 },
};

// 角色卡显示行：duty · arrangement · deliverables
export function roleLine(role) {
  if (!role) return '';
  return [role.duty, role.arrangement, role.deliverables].filter(Boolean).join(' · ');
}

// ---- 以下为 Human 操作入口（POST /api/team/confirm）的数据组装 ----

// 组装 confirm 输入：只按四种正式合同组装，不拼接 Shell。
// open-plan {owner,task,version}；approve-roles {room,expected_revision}；
// save-role {room,home,expected_revision,role}；accept-goal {room,task,artifact,basis,remaining,read_to}
export function confirmInput(action, context) {
  const c = context || {};
  switch (action) {
    case 'open-plan':
      return { owner: c.owner, task: c.task, version: c.version };
    case 'approve-roles':
      return { room: c.room, expected_revision: c.expected_revision };
    case 'save-role':
      return { room: c.room, home: c.home, expected_revision: c.expected_revision, role: c.role };
    case 'accept-goal':
      return { room: c.room, task: c.task, artifact: c.artifact, basis: c.basis, remaining: c.remaining, read_to: c.read_to };
    default:
      return null;
  }
}

// Human 操作结果的三种可见状态：applied / cancelled / failed
export function actionOutcome(value) {
  if (!value) return { kind: 'failed', text: '请求未完成' };
  if (value.ok === true && (value.applied === true || value.state === 'applied' || value.result === 'applied'))
    return { kind: 'applied', text: '已生效' };
  if (value.cancelled === true || value.state === 'cancelled' || value.result === 'cancelled')
    return { kind: 'cancelled', text: 'Human 取消了操作' };
  if (value.ok === false) {
    // 冲突（revision 不匹配等）与普通错误分别可见
    const code = value.error_code || '';
    if (code.includes('revision') || code.includes('conflict') || code.includes('stale'))
      return { kind: 'conflict', text: '版本冲突：' + (value.error || '请刷新后重试') };
    return { kind: 'failed', text: value.error || '操作失败' };
  }
  return { kind: 'failed', text: '结果未确认' };
}

// cards 显示辅助：从 team cards 投影出成员实际 Task 状态与成果
export function cardTaskLine(card) {
  if (!card || !card.task) return '';
  const t = card.task;
  const parts = [];
  if (t.state === 'doing') parts.push('进行中');
  else if (t.state === 'done') parts.push('已完成');
  else if (t.state === 'todo') parts.push('待接手');
  else if (t.state) parts.push(t.state);
  if (t.artifact_ref) parts.push(t.artifact_ref);
  if (t.title) parts.push(t.title);
  return parts.join(' · ');
}
