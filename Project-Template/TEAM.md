---
schema: paos-workflow/v1
id: template-team
title: TEAM 模板
description: 项目成员的职责与专长，联系和当前行动直达本人工位。
tags: template, team, peers
status: active
version: 8
---

# 项目 <project-id> · 成员

## 当前成员

### <home-id>

- 成员状态：<实际在队/暂停状态，不表示在线>。
- 职责/专长：<Coordinator 确认职责，本人补充专长>。
- 工位与联系：[ENTRY](Workstations/<home-id>/ENTRY.md)。
- 当前行动：[TODO](Workstations/<home-id>/TODO.md)。

## 维护

Coordinator 维护成员归属与职责，本人维护专长。这里只列实际成员；目录存在不等于已经登记。小节标题用完整 Home ID，`职责/专长` 供 CLI 按需读取。

当前任务只读本人 TODO；Harness 和联系入口读 ENTRY，原生绑定、STOP 与接收器状态读 Contact。不抄 Session ID、端口或在线状态，不把配置存在当作已接手。Rooter 是安装级支持，不列入项目成员。

只更新本人负责的小节，保留其他有效内容。历史成员按已有交接记录追溯，不与当前成员混列。

成员或职责变化后，使用当前安装的 `System/PROJECTS.md#更新与检查` 中的正式写者重建并检查聚合页；System 位置从本人 ENTRY 的安装描述定位。原件缺失时保留明确断点，不用 ENTRY 猜填另一份职责。
