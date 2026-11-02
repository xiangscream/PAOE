---
schema: paos-workflow/v1
id: template-workstation-todo
title: TODO v4：Obsidian 原生工位
status: active
version: 11
description: TODO v4 的格式与编辑入口；信息职责与工作行为链接唯一工作循环。
tags: template, todo, current, obsidian
---

# 工位 TODO v4

TODO 是本工位当前行动的原件，可由 Human 在 Obsidian 编辑、由 Agent 沿既有写者更新。各区职责、SSOT、主动求助与收口规则见 [Agent 工作循环](../Workflows/wf-agent-work-cycle.md#工作事实)；本页只定义格式和编辑方式，不复制一套行为规则。

复制下面正文到已登记 Home 的 `TODO.md`，填写真实身份。Rooter 的 `home_kind` 为 `rooter`，`project_id` 为空字符串。

```markdown
---
schema: "paos-todo/v4"
home_kind: "project_agent"
home_id: "3002-s010"
project_id: "3002"
---

# Pinned

- 项目当前入口：[[INDEX]]。
- 持续有效的本人要求：引用准确的 Human 原始输入。

# Current

- **Objective:** 更新项目口径并处理未完成输入
- **Next action:** T-001：阅读新增日会并核对原文
- **Waiting:**
- **Inflight:**
- **Context refs:**
  - [[Materials/日会记录]]
- **Result refs:**

# Tasks

- [/] **T-001** · 从日会提取影响下一步的结论
  - **Source refs:**
    - [[Materials/日会记录]]
  - **Artifact:** [[Works/日会整理]]
```

## 格式

- frontmatter 只含 `schema`、`home_kind`、`home_id`、`project_id` 四项身份属性。
- `Pinned` 可写正常 Markdown、长原话、引用和二级标题。不要嵌套保留的 `# Pinned`、`# Current`、`# Tasks` 一级标题。
- `Current` 可用字段为 `Objective`、`Next action`、`Waiting`、`Inflight`、`Context refs`、`Result refs`、`Updated at`；仅前两项必填。不要添加已退出的 `stage`、`generated` 等字段。引用列表使用示例中的缩进。
- `Tasks` 的状态唯一来自 checkbox：`[ ]` todo、`[/]` doing、`[?]` waiting、`[x]` done、`[-]` cancelled，不再另写 `state`。特殊标记的视觉样式可能依赖 Obsidian 主题/插件，文件解析不依赖它们。
- 任务使用稳定 ID，形如 `- [/] **T-001** · 描述`。可选子字段是 `Waiting`、`Result`、`Artifact`、`Source refs`、`Acceptance refs`、`Notify after`；按需填写，不为每项任务制造全部字段。长说明放 Pinned 或成果原件，以链接引用。

## 编辑

人工可以直接改当前原件的文字、勾选框和引用，保持上述机器可读区格式。Agent 自动更新优先采用已有入口：

| 修改范围 | 入口与行为 |
| --- | --- |
| 只改 Current | `attention todo-update`，Rooter 用 `rooter-todo-update`；只改提交字段，保留 Pinned、Tasks 原字节 |
| 修改 Pinned 或 Tasks | `attention todo-write`，Rooter 用 `rooter-todo-write`；完整载荷保留身份、其他任务与原引用 |
| 防止旧内容覆盖 | 完整写入前读最新原件，用 `--expected-fingerprint` 提交原始字节 SHA-256；冲突后回读，不强行覆盖 |
| 格式损坏 | 保留原件与具体错误，整理独立候选后验证写回；不先清空唯一 TODO |

`Updated at` 在 Current 真正变化时由现有写者更新；no-op 不刷新，不用它表示 Harness 实时活跃。`todo-write` 继续验证身份、状态与引用，不接受旧 v3。旧工位转换仍走既有离线候选工具，本模板不自动修改生产工位。
