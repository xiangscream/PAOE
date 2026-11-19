---
schema: paos-workflow/v1
id: guide-work-method
title: 工作入口：按需查找方法、工具与同事
description: 按需查找已登记方法、工具、项目经验与协作入口；开工与恢复请直接读取项目生效 AGENTS。
tags: guide, work-method, entry
status: active
version: 18
---

# 工作入口与资源检索

<!-- paoe:human-intro:start -->
> [!info] 给使用者
> 不确定该用哪种方法或工具做事时，从这里开始。它指引你如何按任务检索可复用的工作流、专业技能与本地工具。
>
> **从这里开始：** 开工恢复请直接读所属项目生效的 `AGENTS.md`；需要寻找方法时查阅下方检索表。
<!-- paoe:human-intro:end -->

<!-- paoe:agent-reference -->
## 操作与参考
<!-- paoe:reading-header:end -->

通用的工作启动、TODO 维护与交付闭环以 **项目生效 AGENTS 公共区** 为准。本页仅作为资源定位的手册。

---

## 按需寻找资源

下列 `paos` 指本人工位 ENTRY 中当前安装的完整 CLI 前缀。

| 需求目标 | 检索命令 | 找到之后的动作 |
| --- | --- | --- |
| **通用流程与多步工作法** | `paos library search "任务关键词" --kind workflow` | 阅读命中文档源文件，选择适合当前任务的深度 |
| **特定专业技能与判断标准** | `paos library search "任务关键词" --kind skill` | 阅读命中的 `SKILL.md` 正文；不强套不相符的技能 |
| **不确定资源类型** | `paos library search "任务关键词"` | 查看返回的类型、摘要与原件路径，再读相关正文 |
| **本机工具与调用入口** | `paos library tools` | 查阅 Tool Catalog；核对本机实际路径、权限与可用状态 |
| **本项目解决过的类似问题** | `paos project experience <项目ID>` | 读取 `Materials/TIPS.md` 经验原件及其适用范围 |
| **查看方法库物理根目录** | `paos library roots show` | 确认 Workflow/Skill/Tool 的实际登记目录 |

---

## 从项目经验追到跨项目经历

项目 TIPS 保存本项目已经确认的做法。要找跨项目教训、Human 原话或旧决定的缘由，从项目 AGENTS 页首进入 EXM 的本机检索方法。具体名称用词面检索；只记得现象时，用任务描述做语义召回。打开命中的原件，核对当时条件、后续纠偏和现在的差别。

Libraries 帮你选择操作步骤，EXM 帮你判断这次为什么这样做。把采用的方法用在产物里，把影响取舍的经历链接放在那项决定旁。已知入口直接复用；资料与当前任务无关时，继续处理手头的事。

## 检索要点与路径解析

1. **关键词选择**：优先描述具体动作或产物类型（如“文档编辑”、“工程变更”、“独立复核”、“spec-writing”）。
2. **路径权威性**：
   - 搜索结果返回的 `source_path` 是当前 CLI 宿主环境（Windows 或 WSL）可直接读取的权威原件绝对路径。
   - `relative_path` 是相对库根的路径；不要相对项目目录随意猜测相邻文件夹。
   - Catalog 与搜索结果为派生索引，**采用方法必须实读源文件正文**，不可仅凭标题或摘要臆断内容。
3. **沿用已有工具**：从 Tool Catalog 取本机入口。在新环境首次使用或发生故障时，核对版本、身份及相应命令。环境已验证时直接处理任务。
