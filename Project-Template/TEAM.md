---
schema: paos-workflow/v1
id: template-team
title: TEAM 模板
description: 项目长期岗位与 Harness 分工的唯一正文（SSOT），联系和当前行动直达本人工位。
tags: template, team, peers
status: active
version: 12
---

# 项目 <project-id> · 成员

> **长期岗位唯一正文（SSOT）**：本页集中维护本项目的长期岗位、专长与实际 Harness，工位入口自动引用此处边界，无需在各工位重复手写 Harness 分工。本轮协作的**临时角色与安排**从 CAT 角色卡与本人 Task 取得，不写进本页。

## 当前成员

### <全局员工号 Sxxx>

- 成员状态：<实际在队 / 暂停 / 人工维护，不表示在线>。
- 职责/专长：<Coordinator 确认职责，本人补充专长>。
- Harness：<实际使用的 Codex / OpenCode / Antigravity / DSH 等；变更时同步>。
- 工位与联系：[ENTRY](Workstations/<全局员工号 Sxxx>/ENTRY.md)。
- 当前行动：[TODO](Workstations/<全局员工号 Sxxx>/TODO.md)。

## 维护约定

- **分工维护**：Coordinator 维护成员归属与长期职责，本人维护专长与实际 Harness。这里只列已登记成员；目录存在不等于已经登记。小节标题与工位路径统一使用安装登记的全局员工号 `Sxxx`，`职责/专长` 供 CLI（`paos peers`）按需读取。
- **单一事实源**：本页只记长期分工，安装级或跨项目支持列为协作入口、不冒充本项目成员（Rooter 为安装级支持，不列入项目成员）。当前任务读本人 `TODO.md`，恢复与联系入口读 `ENTRY.md`，原生绑定、STOP 与接收状态读 Contact，临时协作角色读 CAT 角色卡；不抄 Session ID、端口或在线状态。
- **局部更新与同步**：只更新本人负责的小节，历史成员沿交接记录追溯。成员或职责变化后，使用当前安装的 `System/PROJECTS.md#更新与检查` 中的正式写者重建并检查聚合页；原件缺失时保留断点，不用 ENTRY 猜填职责。
