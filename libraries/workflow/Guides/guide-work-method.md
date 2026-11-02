---
schema: paos-workflow/v1
id: guide-work-method
title: 工作入口：必读循环与按需方法
description: 恢复进入唯一工作循环；按任务查找已登记的方法、工具、项目经验与协作入口。
tags: guide, work-method, entry
status: active
version: 16
---

# 工作入口

从固定 ENTRY 进入 [Agent 工作循环](../Workflows/wf-agent-work-cycle.md)、本人角色规则、TODO 和当前输入。恢复、TODO 职责、主动求助与收口只在工作循环维护；本页提供导航，不要求通读所有指南或 Catalog。

| 要做什么 | 直接打开 |
| --- | --- |
| 恢复身份、当前工作或压缩后接续 | [工作循环·恢复](../Workflows/wf-agent-work-cycle.md#恢复) |
| 判断事实放哪里、维护 Pinned/Current/Tasks | [工作循环·工作事实](../Workflows/wf-agent-work-cycle.md#工作事实) · [TODO 格式](../Templates/workstation-todo.md) |
| 找可复用流程、专业方法或工具 | [按需寻找资源](#按需寻找资源) |
| 找专业同事、Coordinator 或 Rooter | [操作入口·联系同事与 Rooter](ops-entry.md#联系同事与-rooter) |
| 发信/提醒/失败动作，维护 Current 与 Notice | [操作入口](ops-entry.md) · [联系并让对方接续](guide-paos-cat-operations.md#联系并让对方接续) |
| 写/改文档、作者归属与版本引用 | [文档编辑](guide-document-editing.md#内容作者与版本)；专业 Skill 沿已登记 Skill 库检索 |
| 归位成果、归档旧版、Git 与日常顺手维护 | [Project 文件与 Git](guide-project-work-world.md#日常顺手维护) |
| 处理对话/日会/Tips 增量 | [日常输入整理](../Workflows/wf-meeting-audio-package.md)；汇报模板从已登记 Skill 库找 `project-progress-sync` |
| 夜间补漏、解除旧等待、经验回用 | [夜间整理](../Workflows/wf-night-maintenance.md) |
| 派工、验收与团队分工 | [Coordinator 工作循环](../Workflows/wf-coordinator-governance-cycle.md) |
| 工具操作异常与写入陷阱 | [工具行为陷阱](guide-tool-pitfalls.md) |
| 安装、运行恢复、采用与研究咨询 | [Rooter 安装](guide-rooter-installation.md) · [升级与采用](guide-upgrade-adoption.md) · [研究与咨询](guide-research-consultation.md) |

## 按需寻找资源

下列 `paos` 指 ENTRY 中当前安装的调用入口；不假定另有 `paoe` 别名。

| 需要什么 | 现有入口 | 找到以后 |
| --- | --- | --- |
| 多步工作方法与实例 | `paos library search "任务关键词" --kind workflow` | 读命中 Workflow 的源文件，选择适合本次任务的深度 |
| 专业判断或操作方法 | `paos library search "任务关键词" --kind skill` | 读命中 Skill 正文；用途不匹配就不强用 |
| 不确定资源类型 | `paos library search "任务关键词"` | 先看类型、用途与路径，再读相关正文 |
| 工具能力和实际入口 | `paos library tools` | 查看当前登记 Tool Catalog；按条目核本机入口和权限 |
| 本项目已经解决的类似问题 | `paos project experience <本人项目ID>` | 回到经验原件及其适用范围；没有经验不造空记录 |
| 库的真实位置 | `paos library roots show` | 使用登记的 Workflow/Skill/Tool 路径，不猜相邻目录 |

关键词优先描述要解决的问题，例如“工程变更”“独立复核”“规格写作”“文档表达”。已知资源 ID 时可直接检索 `spec-writing`、`clean-writing` 等。搜索结果可直接使用 `source_locator` 打开权威源文件；`relative_path` 仍相对该项 `library_kind` 对应的登记库根，可通过 `library roots show` 交叉核对。Windows/WSL 路径按当前安装环境转换，不相对项目或当前 shell 目录猜测。Catalog/搜索结果是派生导航；采用方法必须读源文件，不能凭名称或摘要推断方法正文。

Workflow、Skill 与 Tool 可以分别登记在不同目录。ENTRY 中的目录链接和本机 Library roots 是定位依据；本指南不使用 `../../skill` 等相邻目录假设，也不把共享正文复制进 Project。搜索无结果、库未登记和源文件不可读是不同情况：前者可换贴近任务的关键词，后两者沿 [安装入口](ops-entry.md)处理。

Tool 条目存在不等于当前机器已安装、已授权或可调用。只核本次需要的入口，不每次扫描所有工具。具体调用按对应正文与安装 CLI 的 `--help`。

当前导航不承载历史，历史材料按需读 [Archive](../Archive/README.md)。
