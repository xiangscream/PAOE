<script>
// PAOE 0.1 任务房前端：团队计划卡 + 角色卡 + 两次放行阶段 + Human 操作入口。
// 数据来源 GET /api/rooms/{room}/team → {team, cards}；
// Human 操作 POST /api/team/confirm {action, receipt_id, input}，由 Core 受信确认流一次生效。
// 本组件不做第二次确认弹窗；错误/冲突/取消分别可见。
import { roleCardState, teamStage, planSummary, planMembers, roleLine, actionOutcome, cardTaskLine, cardGroup, allSeatRoles, canShowAcceptGoal, reviewKey, reviewMatches } from '../../../team-select.mjs';

export default {
  name: 'TeamPanel',
  props: {
    team: { type: Object, default: null },
    cards: { type: Object, default: null },       // {HOME: {role, task, current, group?}}
    people: { type: Array, default: () => [] },
    room: { type: String, default: '' },          // 当前任务房；由页面显式传入
    readTo: { type: Number, default: 0 },         // 当前已读游标
    reviews: { type: Object, default: () => ({}) }, // 已展示的 review 快照，按 action+input 绑定
    open: { type: Boolean, default: true },
    actionBusy: { type: String, default: '' },     // 当前在途的 action 名（'approve-roles' 等）
    actionName: { type: String, default: '' },      // 最近一次完成的 action 名，区分本次保存与其他动作
    actionOutcome: { type: Object, default: null }, // {kind, text} 最近一次操作结果
  },
  emits: ['toggle', 'confirm', 'review'],
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
        group: cardGroup(this.cards?.[entry.home]),
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
    approveInput() {
      return { room: this.room, expected_revision: this.team?.revision || 0 };
    },
    approveReview() { return this.reviews[reviewKey('approve-roles', this.approveInput)]; },
    approveReady() { return reviewMatches(this.approveReview, 'approve-roles', this.approveInput); },
    saveInput() {
      if (!this.editHome) return null;
      const entry = this.team?.roles?.[this.editHome];
      return {
        room: this.room,
        home: this.editHome,
        expected_revision: entry?.revision || 0,
        role: {
          duty: this.editDuty.trim(),
          arrangement: this.editArrangement.trim(),
          deliverables: this.editDeliverables.trim(),
        },
      };
    },
    saveReview() { return this.saveInput ? this.reviews[reviewKey('save-role', this.saveInput)] : null; },
    saveReady() { return !!this.saveInput && reviewMatches(this.saveReview, 'save-role', this.saveInput); },
    acceptInput() {
      if (!this.acceptArtifact?.trim() || !this.acceptBasis?.trim()) return null;
      return {
        room: this.room,
        task: this.team?.plan?.task || '',
        artifact: this.acceptArtifact.trim(),
        basis: this.acceptBasis.trim(),
        remaining: this.acceptRemaining?.trim() || 'none',
        read_to: this.readTo,
      };
    },
    acceptReview() { return this.acceptInput ? this.reviews[reviewKey('accept-goal', this.acceptInput)] : null; },
    acceptReady() { return !!this.acceptInput && reviewMatches(this.acceptReview, 'accept-goal', this.acceptInput); },
  },
  watch: {
    team: {
      handler() { if (this.canApproveRoles) this.queueReview('approve-roles', this.approveInput); },
      deep: true, immediate: true,
    },
    acceptInput: {
      handler(input) { if (input) this.queueReview('accept-goal', input, 250); },
      deep: true,
    },
    saveInput: {
      handler(input) { if (input) this.queueReview('save-role', input, 250); },
      deep: true,
    },
    actionOutcome: {
      // 仅本次 save-role 明确 applied 才退出编辑；失败/冲突/取消/未知保留草稿。
      // 其他动作的旧成功结果不当作本次保存成功。
      handler(outcome) {
        if (this.actionName !== 'save-role' || !outcome) return;
        if (outcome.kind === 'applied' && this.editHome && this.editHome === this.savingHome) {
          this.editHome = '';
        }
        this.savingHome = '';
      },
    },
  },
  data() {
    return {
      editHome: '',
      editDuty: '', editArrangement: '', editDeliverables: '',
      acceptArtifact: '', acceptBasis: '', acceptRemaining: '',
      reviewTimer: 0,
      savingHome: '',
    };
  },
  beforeUnmount() { clearTimeout(this.reviewTimer); },
  methods: {
    nameOf(id) {
      const person = this.people.find(p => p.staff_number === id || p.home_id === id || p.number === id);
      return person?.name || id;
    },
    taskLine(task) { return cardTaskLine({ task }); },
    queueReview(action, input, delay = 0) {
      if (!input) return;
      clearTimeout(this.reviewTimer);
      if (!delay) { this.$emit('review', { action, input }); return; }
      this.reviewTimer = setTimeout(() => this.$emit('review', { action, input }), delay);
    },
    approveRoles() {
      if (!this.approveReady) return;
      this.$emit('confirm', { action: 'approve-roles', input: this.approveInput, choice: 'approve' });
    },
    acceptGoal() {
      if (!this.acceptReady) return;
      this.$emit('confirm', { action: 'accept-goal', input: this.acceptInput, choice: 'approve' });
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
      if (!this.saveReady) return;
      // 提交后保留编辑对象与已填字段；仅本次保存明确 applied 后由 actionOutcome 关闭。
      this.savingHome = this.editHome;
      this.$emit('confirm', { action: 'save-role', input: this.saveInput, choice: 'approve' });
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
        <template v-if="canApproveRoles">
          <div class="review-box" data-testid="review-approve-roles">
            <small v-if="approveReview?.status==='loading'">正在读取本次审阅内容…</small>
            <small v-else-if="approveReview?.status==='error'" class="review-error">审阅失败：{{approveReview.error}}
              <button class="text-button" @click="$emit('review',{action:'approve-roles',input:approveInput})">重试</button></small>
            <template v-else-if="approveReady">
              <small>本次审阅版本 r{{team.revision}}</small>
              <pre v-if="approveReview.explanation">{{approveReview.explanation}}</pre>
            </template>
            <small v-else>审阅内容未就绪</small>
          </div>
          <button class="primary-button small" :disabled="!!actionBusy || !approveReady" data-testid="btn-approve-roles"
                  @click="approveRoles">{{actionBusy==='approve-roles'?'处理中…':'放行角色卡（第二次放行）'}}</button>
        </template>
      </div>
      <div v-if="canAcceptGoal" class="accept-goal-form" data-testid="accept-goal-form">
        <label>成果原件<input v-model="acceptArtifact" type="text" placeholder="如 result.md（必填）"/></label>
        <label>验收依据<input v-model="acceptBasis" type="text" placeholder="如 basis.md（必填）"/></label>
        <label>剩余事项<input v-model="acceptRemaining" type="text" placeholder="无则留空"/></label>
        <div class="review-box" data-testid="review-accept-goal">
          <small v-if="!acceptInput">填写成果原件与验收依据后读取本次审阅内容。</small>
          <small v-else-if="acceptReview?.status==='loading'">正在读取本次审阅内容…</small>
          <small v-else-if="acceptReview?.status==='error'" class="review-error">审阅失败：{{acceptReview.error}}
            <button class="text-button" @click="$emit('review',{action:'accept-goal',input:acceptInput})">重试</button></small>
          <template v-else-if="acceptReady">
            <small>本次审阅版本</small>
            <pre v-if="acceptReview.explanation">{{acceptReview.explanation}}</pre>
          </template>
          <small v-else>审阅内容未就绪</small>
        </div>
        <button class="primary-button small" :disabled="!!actionBusy || !acceptReady" data-testid="btn-accept-goal"
                @click="acceptGoal">{{actionBusy==='accept-goal'?'提交中…':'验收目标'}}</button>
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
            <div class="review-box" data-testid="review-save-role">
              <small v-if="saveReview?.status==='loading'">正在读取本次审阅内容…</small>
              <small v-else-if="saveReview?.status==='error'" class="review-error">审阅失败：{{saveReview.error}}
                <button class="text-button" @click="$emit('review',{action:'save-role',input:saveInput})">重试</button></small>
              <template v-else-if="saveReady">
                <small>本次审阅版本 r{{saveInput.expected_revision}}</small>
                <pre v-if="saveReview.explanation">{{saveReview.explanation}}</pre>
              </template>
              <small v-else>审阅内容未就绪</small>
            </div>
            <div class="edit-actions">
              <button class="secondary-button small" @click="cancelEdit">取消</button>
              <button class="primary-button small" :disabled="!!actionBusy || !saveReady" @click="saveRole">{{actionBusy==='save-role'?'保存中…':'保存'}}</button>
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
            <!-- F88：直接映射后端 todo.groups 的同名组；不在前端另存 TODO。 -->
            <div v-if="entry.group" class="work-group" data-testid="work-group">
              <small class="group-name">工作：{{entry.group.name || '零散事项'}}</small>
              <ul v-if="entry.group.tasks.length" class="group-tasks">
                <li v-for="task in entry.group.tasks" :key="task.id || task.title">{{taskLine(task)}}</li>
              </ul>
              <small v-if="entry.group.rooms.length" class="group-rooms">CAT {{entry.group.rooms.join(' · ')}}</small>
            </div>
            <p v-else-if="entry.taskLine" class="task-line" data-testid="task-line">{{entry.taskLine}}</p>
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
.action-bar{display:flex;gap:8px;flex-wrap:wrap;align-items:flex-start}
.action-bar .review-box{flex:1 1 100%}
.review-box{display:grid;gap:4px;min-width:0;padding:7px 9px;border:1px solid var(--line-soft);border-radius:8px;background:var(--surface)}
.review-box small{font-size:10.5px;opacity:.62}
.review-box pre{margin:0;max-height:140px;overflow:auto;padding:6px 8px;border-radius:7px;background:#fff;font:inherit;font-size:10.5px;line-height:1.5;white-space:pre-wrap;word-break:break-word}
.review-box .review-error{color:#c62828;opacity:1}
.review-box .text-button{margin-left:6px;font-size:10.5px}
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
.outcome-recorded{background:#fff8e1;color:#8d6e00}
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
.work-group{display:grid;gap:4px;padding:7px 9px;border-radius:8px;background:var(--surface)}
.group-name{font-size:10.5px;font-weight:600;opacity:.7}
.group-tasks{margin:0;padding-left:15px;font-size:10.5px;opacity:.65;line-height:1.55}
.group-rooms{font-size:10px;opacity:.5}
.edit-role{align-self:flex-start}
.role-edit{display:flex;flex-direction:column;gap:8px}
.role-edit label{display:grid;gap:4px;font-size:11px;font-weight:600;opacity:.7}
.role-edit input{border:1px solid var(--line-soft);border-radius:6px;padding:6px 8px;font-size:12px;background:#fff;color:inherit}
.edit-actions{display:flex;gap:6px;justify-content:flex-end}
.team-receipt-info{display:flex;gap:12px;font-size:10px;opacity:.5}
@media(max-width:900px){.team-panel{margin:10px 12px 0}.role-grid{grid-template-columns:1fr}}
</style>
