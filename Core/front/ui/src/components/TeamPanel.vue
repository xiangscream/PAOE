<script>
// PAOE 0.1 任务房前端：团队计划卡 + 角色卡 + 两次放行阶段 + Human 操作入口。
// 数据来源 GET /api/rooms/{room}/team → {team, cards}；
// Human 操作 POST /api/team/confirm {action, receipt_id, input}，由 Core 受信确认流一次生效。
// 本组件不做第二次确认弹窗；错误/冲突/取消分别可见。
import { roleCardState, teamStage, planSummary, planMembers, roleLine, confirmInput, actionOutcome, cardTaskLine, allSeatRoles, canShowAcceptGoal } from '../../../team-select.mjs';

export default {
  name: 'TeamPanel',
  props: {
    team: { type: Object, default: null },
    cards: { type: Object, default: null },       // {HOME: {home, role, task:{state,artifact_ref,title,...}}}
    people: { type: Array, default: () => [] },
    open: { type: Boolean, default: true },
    actionBusy: { type: String, default: '' },     // 当前在途的 action 名（'approve-roles' 等）
    actionOutcome: { type: Object, default: null }, // {kind, text} 最近一次操作结果
  },
  emits: ['toggle', 'confirm'],
  computed: {
    stage() { return teamStage(this.team); },
    summary() { return planSummary(this.team?.plan); },
    members() { return planMembers(this.team?.plan); },
    roleEntries() {
      return allSeatRoles(this.team).map(entry => ({
        ...entry,
        memberName: this.nameOf(entry.home),
        line: roleLine(entry?.role),
        taskLine: cardTaskLine(this.cards?.[entry.home]),
      }));
    },
    canApproveRoles() {
      return this.team && !this.team.accepted && !this.team.owner_acceptance &&
        this.roleEntries.some(e => e.state.kind === 'draft');
    },
    canAcceptGoal() {
      return canShowAcceptGoal(this.team, this.isOwner);
    },
    isOwner() {
      return false; // 网页是 Human 身份，owner 角色由 close_policy 联动判定
    },
    editingHome() { return this.editHome || ''; },
  },
  data() {
    return {
      editHome: '',
      editDuty: '', editArrangement: '', editDeliverables: '',
      acceptArtifact: '', acceptBasis: '', acceptRemaining: '',
    };
  },
  methods: {
    nameOf(id) {
      const person = this.people.find(p => p.staff_number === id || p.home_id === id || p.number === id);
      return person?.name || id;
    },
    emitConfirm(action, context) {
      const input = confirmInput(action, context);
      if (input) this.$emit('confirm', { action, input });
    },
    approveRoles() {
      this.emitConfirm('approve-roles', {
        room: this.team?.plan?.task ? this.$parent?.state?.id || '' : '',
        expected_revision: this.team?.revision || 0,
      });
    },
    acceptGoal() {
      const state = this.$parent?.state;
      if (!this.acceptArtifact?.trim() || !this.acceptBasis?.trim()) return;
      this.emitConfirm('accept-goal', {
        room: state?.id || '',
        task: this.team?.plan?.task || '',
        artifact: this.acceptArtifact.trim(),
        basis: this.acceptBasis.trim(),
        remaining: this.acceptRemaining?.trim() || 'none',
        read_to: state?.cursor || 0,
      });
    },
    startEdit(home) {
      const entry = this.team?.roles?.[home];
      this.editHome = home;
      this.editDuty = entry?.role?.duty || '';
      this.editArrangement = entry?.role?.arrangement || '';
      this.editDeliverables = entry?.role?.deliverables || '';
    },
    cancelEdit() { this.editHome = ''; },
    saveRole() {
      if (!this.editHome) return;
      const entry = this.team?.roles?.[this.editHome];
      this.emitConfirm('save-role', {
        room: this.$parent?.state?.id || '',
        home: this.editHome,
        expected_revision: entry?.revision || 0,
        role: { duty: this.editDuty.trim(), arrangement: this.editArrangement.trim(), deliverables: this.editDeliverables.trim() },
      });
      this.editHome = '';
    },
  },
};
</script>

<template>
  <section v-if="team" class="team-panel" :class="{collapsed:!open}" aria-label="团队计划与角色卡" data-testid="team-panel">
    <header class="team-head">
      <button type="button" class="team-toggle" :aria-expanded="open" @click="$emit('toggle')">
        <strong>团队计划</strong>
        <span v-if="stage.label" class="stage" :class="'tone-'+stage.tone" data-testid="team-stage">{{stage.label}}</span>
        <small v-if="summary">{{summary}}</small>
      </button>
      <span v-if="stage.hint" class="stage-hint">{{stage.hint}}</span>
    </header>
    <div v-if="open" class="team-body">
      <div v-if="team.plan?.title" class="plan-title" data-testid="plan-title">{{team.plan.title}}</div>
      <p v-if="stage.hint" class="stage-description">{{stage.hint}}</p>

      <!-- Human 操作入口 -->
      <div v-if="actionOutcome" class="action-outcome" :class="'outcome-'+actionOutcome.kind" role="status" data-testid="action-outcome">
        {{actionOutcome.text}}
      </div>
      <div class="action-bar">
        <button v-if="canApproveRoles" class="primary-button small" :disabled="!!actionBusy" data-testid="btn-approve-roles"
                @click="approveRoles">{{actionBusy==='approve-roles'?'处理中…':'放行角色卡（第二次放行）'}}</button>
      </div>
      <div v-if="canAcceptGoal" class="accept-goal-form" data-testid="accept-goal-form">
        <label>成果原件<input v-model="acceptArtifact" type="text" placeholder="如 result.md（必填）"/></label>
        <label>验收依据<input v-model="acceptBasis" type="text" placeholder="如 basis.md（必填）"/></label>
        <label>剩余事项<input v-model="acceptRemaining" type="text" placeholder="无则留空"/></label>
        <button class="primary-button small" :disabled="!!actionBusy || !acceptArtifact.trim() || !acceptBasis.trim()" data-testid="btn-accept-goal"
                @click="acceptGoal">{{actionBusy==='accept-goal'?'等待确认…':'验收目标'}}</button>
      </div>

      <div v-if="roleEntries.length" class="role-grid" role="list">
        <article v-for="entry in roleEntries" :key="entry.home" class="role-card" :class="'card-'+entry.state.kind" role="listitem" :data-home="entry.home">
          <header>
            <strong>{{entry.memberName}}</strong>
            <span v-if="entry.state.revision" class="revision">r{{entry.state.revision}}</span>
            <span class="role-status" :class="'status-'+entry.state.kind" data-testid="role-status">{{entry.state.label}}</span>
          </header>

          <!-- 编辑表单 -->
          <div v-if="editingHome===entry.home" class="role-edit" data-testid="role-edit">
            <label>职责<input v-model="editDuty" type="text" placeholder="做什么"/></label>
            <label>安排<input v-model="editArrangement" type="text" placeholder="怎么做"/></label>
            <label>交付物<input v-model="editDeliverables" type="text" placeholder="交什么"/></label>
            <div class="edit-actions">
              <button class="secondary-button small" @click="cancelEdit">取消</button>
              <button class="primary-button small" :disabled="!!actionBusy" @click="saveRole">{{actionBusy==='save-role'?'保存中…':'保存'}}</button>
            </div>
          </div>

          <!-- 只读角色 -->
          <template v-else>
            <dl v-if="entry.role">
              <div v-if="entry.role.duty"><dt>职责</dt><dd>{{entry.role.duty}}</dd></div>
              <div v-if="entry.role.arrangement"><dt>安排</dt><dd>{{entry.role.arrangement}}</dd></div>
              <div v-if="entry.role.deliverables"><dt>交付物</dt><dd>{{entry.role.deliverables}}</dd></div>
            </dl>
            <p v-else class="role-empty">{{entry.state.hint}}</p>
            <p v-if="entry.taskLine" class="task-line" data-testid="task-line">{{entry.taskLine}}</p>
            <button v-if="team.accepted!==true" class="text-button edit-role" :data-home="entry.home" @click="startEdit(entry.home)">调整角色</button>
          </template>
        </article>
      </div>

      <div class="team-receipt-info">
        <small v-if="team.roles_receipt">角色回执 {{team.roles_receipt}}</small>
        <small v-if="team.owner_acceptance">验收回执 {{team.owner_acceptance}}</small>
        <small v-if="team.revision !== undefined">团队 r{{team.revision}}</small>
      </div>
    </div>
  </section>
</template>

<style scoped>
button,input{font:inherit}
button{cursor:pointer}
.team-panel{margin:12px 20px 0;border:1px solid var(--line-soft);border-radius:12px;background:var(--surface);overflow:hidden}
.team-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 14px;border-bottom:1px solid var(--line-soft);background:#fff}
.team-toggle{display:inline-flex;align-items:center;gap:10px;min-width:0;border:0;background:transparent;color:inherit;padding:0;text-align:left}
.team-toggle strong{font-size:13px;font-weight:700}
.team-toggle small{font-size:10.5px;opacity:.65;white-space:nowrap}
.stage{padding:2px 8px;border-radius:999px;font-size:10px;font-weight:600;white-space:nowrap;flex-shrink:0}
.tone-draft{background:#fff3e0;color:#b47923}
.tone-released{background:#e8f5e9;color:#1b7a3d}
.tone-accepted{background:#e3f2fd;color:#1565c0}
.stage-hint{font-size:10.5px;opacity:.6;white-space:nowrap}
.team-body{padding:12px 14px 14px;display:flex;flex-direction:column;gap:10px}
.plan-title{font-size:14.5px;font-weight:600;line-height:1.5}
.stage-description{margin:0;font-size:11.5px;opacity:.66;line-height:1.6}
.action-bar{display:flex;gap:8px;flex-wrap:wrap}
.accept-goal-form{display:flex;flex-direction:column;gap:6px;padding:10px;border:1px solid var(--line-soft);border-radius:10px;background:#fff}
.accept-goal-form label{display:grid;gap:3px;font-size:11px;font-weight:600;opacity:.7}
.accept-goal-form input{border:1px solid var(--line-soft);border-radius:6px;padding:5px 8px;font-size:12px;background:#fff;color:inherit}
.accept-goal-form .primary-button{align-self:flex-end}
.primary-button{display:inline-flex;align-items:center;justify-content:center;background:var(--accent);color:#fff;border:1px solid var(--accent);border-radius:8px;min-height:34px;padding:7px 14px;font-size:12px;font-weight:600}
.primary-button:disabled{opacity:.5}
.primary-button:hover:not(:disabled){filter:brightness(1.06)}
.secondary-button{display:inline-flex;align-items:center;justify-content:center;background:#fff;color:inherit;border:1px solid var(--line-soft);border-radius:8px;min-height:34px;padding:7px 13px;font-size:12px}
.secondary-button:hover{background:var(--surface)}
.text-button{background:transparent;border:0;color:var(--accent);padding:5px 0;font-size:11px;cursor:pointer}
.text-button:hover{text-decoration:underline}
.action-outcome{padding:8px 12px;border-radius:8px;font-size:12px;line-height:1.5}
.outcome-applied{background:#e8f5e9;color:#1b7a3d}
.outcome-cancelled{background:#fff3e0;color:#b47923}
.outcome-conflict{background:#fce4ec;color:#c62828}
.outcome-failed{background:#ffebee;color:#c62828}
.role-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:8px}
.role-card{border:1px solid var(--line-soft);border-radius:10px;padding:10px 12px;background:#fff;min-width:0;display:flex;flex-direction:column;gap:8px}
.role-card header{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.role-card header strong{font-size:12.5px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.revision{font-size:10px;opacity:.5}
.role-status{font-size:10px;padding:2px 7px;border-radius:999px;font-weight:600;flex-shrink:0}
.status-empty{background:var(--surface);color:var(--ink2)}
.status-draft{background:#fff3e0;color:#b47923}
.status-approved{background:#e8f5e9;color:#1b7a3d}
.role-card dl{margin:0;display:grid;gap:5px}
.role-card dl>div{display:grid;grid-template-columns:48px 1fr;gap:6px;font-size:11.5px;line-height:1.55}
.role-card dt{font-weight:600;opacity:.55}
.role-card dd{margin:0;min-width:0;word-break:break-word}
.role-empty{margin:0;font-size:11px;opacity:.55;line-height:1.5}
.task-line{margin:0;font-size:10.5px;opacity:.6;line-height:1.5}
.edit-role{align-self:flex-start}
.role-edit{display:flex;flex-direction:column;gap:8px}
.role-edit label{display:grid;gap:4px;font-size:11px;font-weight:600;opacity:.7}
.role-edit input{border:1px solid var(--line-soft);border-radius:6px;padding:6px 8px;font-size:12px;background:#fff;color:inherit}
.edit-actions{display:flex;gap:6px;justify-content:flex-end}
.team-receipt-info{display:flex;gap:12px;font-size:10px;opacity:.5}
@media(max-width:900px){.team-panel{margin:10px 12px 0}.role-grid{grid-template-columns:1fr}}
</style>
