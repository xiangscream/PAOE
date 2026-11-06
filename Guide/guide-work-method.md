---
schema: paos-workflow/v1
id: guide-work-method
title: 工作入口：按需查找方法、工具与同事
description: 按需查找已登记方法、工具、项目经验与协作入口；恢复直接读取项目 AGENTS。
tags: guide, work-method, entry
status: active
version: 17
---

# 工作入口

<!-- paoe:human-intro:start -->
> [!info] 给使用者
> 不确定该用哪种方法做事时，从这里开始。它按任务用途带你找到合适的工作流、技能和工具说明。
>
> **从这里开始：** 按下面的适用范围和步骤使用；需要执行时让 Agent 从“操作与参考”继续。
<!-- paoe:human-intro:end -->

<!-- paoe:agent-reference -->
## 操作与参考
<!-- paoe:reading-header:end -->

当前工作的启动、恢复、TODO 和交付规则以**实际项目根 AGENTS 公共区**为准。此页提供按任务查找资源的路径，非必读工作循环；Rooter 按 System 工位恢复。

| 当前问题 | 直接使用 |
| --- | --- |
| 恢复、接班、当前目标与 TODO | 先读项目生效 AGENTS、INDEX、本人 ENTRY/TODO |
| 需要 Workflow/Skill/Tool 或项目经验 | [按需寻找资源](#按需寻找资源) |
| 找专业成员/协调者/Rooter | [联系同事与 Rooter](ops-entry.md#联系同事与-rooter) |
| Mail、Notice、Contact/Wake 与失败排查 | [通信操作](guide-paos-cat-operations.md) |
| 项目成果归位、归档、Git | [项目工作世界](guide-project-work-world.md) |
| 发布采用与 Runtime 接班 | [发布采用](guide-upgrade-adoption.md) · [Runtime 交接](guide-runtime-handoff.md) |
| Coordinator 或维护专项 | [Coordinator](wf-coordinator-governance-cycle.md) · [夜间整理](wf-night-maintenance.md) |
| 其它工具行为异常 | [工具陷阱](guide-tool-pitfalls.md) |

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

关键词优先描述要解决的问题，例如“工程变更”“独立复核”“规格写作”“文档表达”。已知资源 ID 时可直接检索 `spec-writing`、`clean-writing` 等。搜索结果的 `source_path` 是当前 CLI 环境可读取的权威原件路径（Windows/WSL 已分别按实际运行环境转换）；`source_locator` 是配置中保留的宿主稳定定位，`relative_path` 仍相对该项 `library_kind` 对应的登记库根。可通过 `library roots show` 交叉核对，不相对项目或当前 shell 目录猜测。Catalog/搜索结果是派生导航；采用方法必须读源文件，不能凭名称或摘要推断方法正文。

Workflow、Skill 与 Tool 可以分别登记在不同目录。ENTRY 中的目录链接和本机 Library roots 是定位依据；本指南不使用 `../../skill` 等相邻目录假设，也不把共享正文复制进 Project。搜索无结果、库未登记和源文件不可读是不同情况：前者可换贴近任务的关键词，后两者沿 [安装入口](ops-entry.md)处理。

Tool 条目存在不等于当前机器已安装、已授权或可调用。需要飞书操作时优先在 Tool Catalog 查 Feishu CLI，打开对应 Tool 文档核本机实际命令、前置条件及调用实例；无法调用时记录原错误联系维护者，避免业务 Agent 自行重复安装。只核本次需要的入口，不每次扫描所有工具。具体调用按对应正文与安装 CLI 的 `--help`。

当前导航不承载历史，历史材料按需读 Archive（`<workflow_root>/Archive/README.md`）。
