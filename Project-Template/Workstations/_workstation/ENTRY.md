---
schema: paos-workflow/v1
id: template-workstation-entry
title: Workstation ENTRY 母本
description: 本人运行定位与业务入口；规则引用项目公共正文，机器配置引用本机登记。
tags: template, workstation, entry
status: active
version: 28
---

# {{staff_number}} · 个人工位入口

## 1. 流程约束与复工

共同运行规则见 [项目 AGENTS](../../AGENTS.md)。
- **Codex Desktop**：执行下方 CLI 前缀加 `orient {{project_id}} {{staff_number}} --resume`，同时准备接收器并读取恢复原文。
- **其他 Harness**（Antigravity / OpenCode / DSH 等）：执行 `orient {{project_id}} {{staff_number}} --read`。

完整阅读返回内容后，按 [本人 TODO](TODO.md) 的 Current 与 Tasks 接续。恢复失败时保留报错交 Rooter，继续推进可独立完成的责任。

| 目标内容 | 快捷入口 |
| --- | --- |
| 当前目标、下一步与成果记录 | [本人 TODO](TODO.md) |
| 项目当前业务口径与同事分工 | [INDEX](../../INDEX.md) · [TEAM 本人条目](../../TEAM.md#{{staff_anchor}}) · {{project_history_link}} |
| 来信原文与通知处理状态 | [Mailbox](mailbox/) · [Notice](notices/) |
| 唤醒、CAT 开房、Libraries 与 EXM 命令速查 | {{guide_index_link}} · {{ops_link}} |
| 查相似经历与旧决定 | [共同背景与 EXM 检索入口](../../AGENTS.md#共同经历) |
| 查找方法与工具能力 | 从[项目 AGENTS 的 Libraries 入口](../../AGENTS.md#libraries-与工具)找方法和本机工具 |

首次入职请读 `notices/README.md`，完成本人 `ONBOARD`。

---

## 2. 本机运行入口

- **Harness**：待本人填写实际运行宿主（如 Antigravity App / Codex Desktop / OpenCode / DSH）。
- **命令环境**：待本人填写实际 Shell 环境（PowerShell / WSL）；PowerShell 请保持 UTF-8 编码。
- **联系与绑定**：待本人填写当前联系状态（生成 `CONTACT.md` / `contact.py`），模型与 STOP 沿现有配置。
- **安装描述**：{{installation_file}}
- **方法库配置**：{{library_roots_config}}
- **CLI 完整调用前缀**：

{{cli_block}}

---

## 3. 业务基础信息

- **员工号**：`{{home_id}}`；**Project**：{{project_id}}
- **Project 根**：{{project_root}}
- **本人工位**：{{home_path}}

岗位职责由 TEAM 维护，业务口径由 INDEX 定位，行动状态由本人 TODO 维护；产出成果写回项目原件。
