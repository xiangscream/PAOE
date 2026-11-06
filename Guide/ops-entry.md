---
schema: paos-workflow/v1
id: ops-entry
title: 操作入口：按目的找命令
description: 定位本人工作、已登记资源、同事与安装级 Rooter；使用现有文件和联系入口。
tags: ops, operations, entry
status: active
version: 33
---

# 操作入口

<!-- paoe:human-intro:start -->
> [!info] 给使用者
> 已经知道要做什么、只想找到操作入口时，查这张导航。具体命令和步骤会链接到对应说明。
>
> **从这里开始：** 按下面的适用范围和步骤使用；需要执行时让 Agent 从“操作与参考”继续。
<!-- paoe:human-intro:end -->

<!-- paoe:agent-reference -->
## 操作与参考
<!-- paoe:reading-header:end -->

`paos` 代表本人 ENTRY 中的当前安装入口。先按目的选入口，只读必要章节；不从命令名称猜协议或手工拼消息文件。

| 目的 | 入口 |
| --- | --- |
| 恢复本人工作 | `orient <project> <home>` / `attention show <project> <home>`；再读 ENTRY、TODO 与当前原输入 |
| 找 Workflow、Skill、Tool 或项目经验 | [工作入口·按需寻找资源](guide-work-method.md#按需寻找资源) |
| 找同事、咨询或交付 | [联系同事与 Rooter](#联系同事与-rooter) |
| 读待处理输入 | `inbox <project> <home>` / `mail list/read` |
| 接手与更新 | `attention takeover` / `todo-update` / `todo-write` / `handle`；[当前页与输入](guide-paos-cat-operations.md#当前页与输入) |
| 查联系或原消息结果 | `status <project> <home>` / `wake status <project> <home>`；已发信使用 `status ... --message-id <原ID>` |
| 项目定位 / 首次登记 | `project show` / `project register --root --coordinator`；不创建项目管理状态 |
| 安装定位或库路径异常 | `install show` / `library roots show` / `health`；[Rooter 安装](guide-rooter-installation.md) |
| 对话、日会、Tips 归位 | 日常输入整理（`<workflow_root>/Workflows/wf-meeting-audio-package.md`） |

## 联系同事与 Rooter

项目成员先用 `paos peers <本人项目ID> <本人Home>` 找已登记同事；职责/专长来自项目 `TEAM.md` 的现行成员小节，CLI 未识别时直接打开其 `team_source.path`。返回值的 `installation_support` 单独列出安装级 Rooter（如已登记）；Rooter 不属于 Project 成员，也不需要创建 rooter 项目。联系人读面不探测在线状态，无法证明对方已接手。

项目 Agent 向已登记 Rooter 提交一个需要接续的新请求，使用已有高层入口：

```sh
paos agent send <本人项目ID> --to rooter-001 --sender-kind agent --sender-id <本人完整HomeID> --subject "安装协助" --body @<UTF-8短请求文件> --message-id <本次唯一ASCII标识> --remind
```

这里第一个位置参数是本次发送的项目上下文，不是 Rooter 的项目 ID。目标由安装登记解析；不要改成 `mail send rooter`，也不要直接往猜测的 Rooter mailbox 写文件。普通项目 Agent 联系其他已登记 Home（包括跨项目）仍用 `agent send <本人项目ID> --to <目标完整HomeID>`，不把目标项目 ID 填在第一个位置；发现目标不在当前 TEAM 时，通过已知项目或 Coordinator 取得准确 Home ID，不遍历其他项目库。完整参数使用同版 `agent send --help`。

只检查 Rooter 的联系配置可用 `paos wake status rooter rooter-001`：此处 `rooter` 是现有 wake 命令的位置参数，目标实际沿安装级 Home 解析，不表示要登记一个 rooter 项目。`attention rooter-show` 等命令是 Rooter 当前页读写入口，不是向它发送任务的替代命令。

需要接续的新交付带 `--remind`。已有 Mail 只补提醒时不重发信件；沿 [操作指南](guide-paos-cat-operations.md#联系并让对方接续)核原 message_id 与本次提醒结果。Mail 落盘、提醒受理、实际接手和工作完成分别成立。未登记、STOP、明确失败和结果未知按回执处理，不通过换通道或循环重试掩盖问题。

对方职责不清时找 Coordinator；安装或原生接收问题找 Rooter；具体专业问题可以直接咨询相应同事。请求写清问题、必要原件和期望结果，工作行为与回到主线的规则见 当前项目 `AGENTS.md` 的公共运行区。

命令用途与已退出入口见 [接口参考](guide-paos-interface-reference.md)。详细投递和提醒语义仍由 [操作指南](guide-paos-cat-operations.md)维护；不要在工位另抄一套。
