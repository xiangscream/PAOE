<script>
// PAOE 0.1 任务房前端：团队计划卡 + 角色卡 + 两次放行阶段展示。
// 数据来源 GET /api/rooms/{room}/team（合同 ②）；本组件只读展示，
// 放行/验收以后台 team.accepted/owner_acceptance 与 roles[].approved 为准。
// Human 操作入口经 Core 受信确认流（组件只发起一次审阅，不做第二次弹窗）。
import { roleCardState, teamStage, planSummary, planMembers, roleLine } from '../../../team-select.mjs';

export default {
  name: 'TeamPanel',
  props: {
    team: { type: Object, default: null },        // {plan, revision, roles:{}, roles_receipt, accepted, owner_acceptance}
    people: { type: Array, default: () => [] },   // 用于显示称呼
    open: { type: Boolean, default: true },
  },
  emits: ['toggle'],
  computed: {
    stage() { return teamStage(this.team); },
    summary() { return planSummary(this.team?.plan); },
    members() { return planMembers(this.team?.plan); },
    roleEntries() {
      const roles = this.team?.roles || {};
      return Object.entries(roles).map(([home, entry]) => ({
        home,
        ...entry,
        state: roleCardState(entry),
        memberName: this.nameOf(home),
        line: roleLine(entry?.role),
      }));
    },
  },
  methods: {
    nameOf(id) {
      const person = this.people.find(p => p.staff_number === id || p.home_id === id || p.number === id);
      return person?.name || id;
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
      <div v-if="roleEntries.length" class="role-grid" role="list">
        <article v-for="entry in roleEntries" :key="entry.home" class="role-card" :class="'card-'+entry.state.kind" role="listitem" :data-home="entry.home">
          <header><strong>{{entry.memberName}}</strong><span v-if="entry.state.revision" class="revision">r{{entry.state.revision}}</span>
            <span class="role-status" :class="'status-'+entry.state.kind" data-testid="role-status">{{entry.state.label}}</span></header>
          <dl v-if="entry.role">
            <div v-if="entry.role.duty"><dt>职责</dt><dd>{{entry.role.duty}}</dd></div>
            <div v-if="entry.role.arrangement"><dt>安排</dt><dd>{{entry.role.arrangement}}</dd></div>
            <div v-if="entry.role.deliverables"><dt>交付物</dt><dd>{{entry.role.deliverables}}</dd></div>
          </dl>
          <p v-else class="role-empty">{{entry.state.hint}}</p>
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
button{font:inherit;cursor:pointer}
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
.role-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px}
.role-card{border:1px solid var(--line-soft);border-radius:10px;padding:10px 12px;background:#fff;min-width:0}
.role-card header{display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap}
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
.team-receipt-info{display:flex;gap:12px;font-size:10px;opacity:.5}
@media(max-width:900px){.team-panel{margin:10px 12px 0}.role-grid{grid-template-columns:1fr}}
</style>
