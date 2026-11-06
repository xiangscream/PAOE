---
schema: paos-workflow/v1
id: template-workstation-entry
title: Workstation ENTRY 母本
description: 本人运行定位与业务入口；规则引用项目公共正文，机器配置引用本机登记。
tags: template, workstation, entry
status: active
version: 22
---

# {{home_id}} · 个人工位入口

## 流程约束

共同运行规则在[项目 AGENTS](../../AGENTS.md)。新会话或压缩后，直接用下方 CLI 前缀加 `orient {{project_id}} {{home_id}} --read`，完整阅读返回原文后按 TODO 接续。

| 要找什么 | 入口 |
| --- | --- |
| 当前目标、下一动作和成果 | [本人 TODO](TODO.md) |
| 业务原件与同事 | [INDEX](../../INDEX.md) · [TEAM 本人条目](../../TEAM.md#{{home_id}}) |
| 来信原文与处理状态 | [Mailbox](mailbox/) · [Notice](notices/) |
| 正常命令与公开联系包 | {{guide_index_link}} · {{ops_link}}；OPS选择“生成本人公开联系包” |
| 方法与工具 | 下方CLI的 `library search` / `library tools`，再读命中的原件 |

首次入职读 `notices/README.md`，完成本人 `ONBOARD`。创建者按母版带入 README、codex.py、opencode.py、wake_entry.py 与入职任务；当前CLI不自动带入。已完成入职的工位保持现状。

### 本机运行入口

- Harness：待本人填写实际运行环境。
- 命令环境：待本人填写实际shell和必要的跨环境入口；PowerShell调用先沿OPS“命令环境”设置UTF-8，再执行CLI。
- 状态与恢复：待本人填写当前正常命令；已生成的 `CONTACT.md` / `contact.py` 提供联系状态，模型、绑定和STOP沿现有配置。
- 安装描述：{{installation_file}}
- 方法库配置：{{library_roots_config}}
- CLI完整调用前缀：

{{cli_block}}

## 业务部分

- Project：{{project_id}}；本人Home：`{{home_id}}`。
- Project根：{{project_root}}。
- 本人工位：{{home_path}}。

岗位与专长由TEAM维护，项目口径由INDEX定位，持续要求和当前行动由本人TODO维护；成果写回项目原件。
