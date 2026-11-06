---
schema: paos-workflow/v1
id: template-workstation-entry
title: Workstation ENTRY 母本
description: 分开说明流程约束与本人业务入口；各项事实引用其原件。
tags: template, workstation, entry
status: active
version: 18
---

# {{home_id}} · 个人工位入口

## 流程约束

软流程规定 Agent 怎样恢复工作、协作、记录和交付。共同规则与恢复步骤读 [项目 AGENTS](../../AGENTS.md)；本页说明工位文件和本人运行入口。

首次入职检查 `notices/` 下的 `README.md`、`codex.py`、`opencode.py`、`wake_entry.py`，以及 TODO 的 `ONBOARD`。缺项请创建者按母版补齐；当前 CLI 不自动带入。

### 工位文件

| 内容 | 用途与位置 |
| --- | --- |
| Home | 本目录，保存本人入口、行动和持久输入；项目资料与成果归项目正文。 |
| [TODO](TODO.md) | Pinned 保存持续要求，Current 保存当前目标与下一步，Tasks 保存任务及结果。恢复工作先读它。 |
| [Notice](notices/) | 输入的关注、已读和处理记录，帮助定位原输入，不代替消息正文或任务完成事实。 |
| [Mailbox](mailbox/) | 收到的 Mail 原文，保留请求、交付与上下文；处理时读取相关原信。 |
| Contact | 本人的联系与运行配置入口；已配置时读本工位 CONTACT.md / contact.py。 |

### 本机运行入口

操作导航：{{guide_index_link}} · {{ops_link}}。生成本人公开联系包，在OPS选择“生成本人公开联系包”。

- Harness：待本人填写实际使用的运行环境。
- 状态与恢复：待本人补充可用命令；绑定、STOP 和接收器状态以 Contact 为准。
- 安装描述：{{installation_file}}
- 方法库配置：{{library_roots_config}}
- CLI 完整调用前缀：

{{cli_block}}

## 业务部分

- 项目：{{project_id}}。
- 本人身份：`{{home_id}}`；负责什么，以 [TEAM 本人条目](../../TEAM.md#{{home_id}}) 为准。
- 项目根：{{project_root}}。
- 本人工位：{{home_path}}。

业务目标、最新口径、重要文档和仓库入口，读 [项目 INDEX](../../INDEX.md) 指向的原件。本人持续要求、当前任务与下一步，读 [TODO](TODO.md)。业务成果写回项目原件。
