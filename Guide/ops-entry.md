---
schema: paos-workflow/v1
id: ops-entry
title: 操作入口：按目的找命令
description: 定位本人工作、已登记资源、同事与安装级 Rooter；使用现有文件和联系入口。
tags: ops, operations, entry
status: active
version: 45
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

`paos`代表当前安装入口：已有Home读本人ENTRY，尚无Home读[已安装机器首次使用](../UPGRADE.md#已安装机器上的首次使用)。先按目的选入口，只读必要章节；不从命令名称猜协议或手工拼消息文件。

## 常用 CLI 速查

以下 PowerShell 命令已在 System 0.2.29 核对，0.2.30 沿用同一接口。先从本人 ENTRY 确认项目号、员工号与 CLI 前缀。下列变量以 REMO 为例，调用前换成本次实际值，各小节按需使用。

~~~powershell
$paos = Join-Path $env:USERPROFILE '.paos/bin/paos.cmd'
$project = '3004'    # 发起方所在项目
$me = 'S042'         # 本人员工号
$peer = 'S043'       # 本次接手人
$targetProject = '3004'  # 接手人所在项目，查对方唤醒状态时用
~~~

### 恢复、收件与记录

| 要做的事 | PowerShell 命令 | 读回或下一步 |
| --- | --- | --- |
| 恢复当前工作 | `& $paos orient $project $me --read` | 实读 AGENTS、INDEX、ENTRY、TODO 及本轮原输入。已登记的 Codex 本人在原 Desktop 用 `--resume`。 |
| 找协作者 | `& $paos peers $project $me --summary` | 按员工号和职责选择接手人。 |
| 收信并读原文 | `& $paos inbox $project $me`，再执行 `& $paos mail read $project $me $mailId` | 从收件结果取真实的 `$mailId` 和对应的 `$noticeId`。 |
| 标读、回信 | `& $paos attention read $project $me $noticeId`，再执行 `& $paos mail reply $project $me $mailId --body '已接手，下一步核对原稿。'` | 反馈写实际下一步或阻碍。需要对方立即行动时用下一节的带提醒交接。 |
| 更新本人 Current | `& $paos attention todo-update $project $me --set 'next_action=核对原稿后交付链接'` | 写当前可执行的一步。Tasks/Pinned 的修改用 `attention todo-write --help` 查看正文与指纹参数。 |
| 处理完成的通知 | `& $paos attention handle $project $me $noticeId --resolution '已交付' --action-ref $artifact` | `$artifact` 填实际成果路径，业务结果写回项目。 |

### 派工与唤醒

新交付一次完成存信和提醒。准备好 UTF-8 原文，将文件路径赋给 `$bodyFile`。本次消息 ID 在重查同一交付时沿用。

~~~powershell
$mailId = 'handoff-' + [guid]::NewGuid().ToString('N')
& $paos --json agent send $project --to $peer --sender-kind agent --sender-id $me --subject '请接续本轮任务' --body ('@' + $bodyFile) --message-id $mailId --remind
~~~

回执中 `native_accepted` 表示原生端受理。被唤醒者读原文后及时回发起人。已有原信，且需在明确失败修复后补一次提醒时，用下列命令；结果不明时先看原交付状态。

~~~powershell
& $paos --json status $project $me --message-id $mailId
& $paos --json wake status $targetProject $peer
& $paos wake trigger $targetProject $peer --source-id $mailId --prompt "请读取原邮箱中的 $mailId，接续原任务并回告。"
~~~

### 开 CAT 房间并组织讨论

先查同题房间。有房间就复用；新议题需要单独讨论时再创建。CAT 是系统级房间，入席使用员工号。

~~~powershell
& $paos cat list
& $paos --json cat create --title '本轮协作议题'
$room = '<上一步返回的实际房间 ID>'
& $paos cat join $room --home $me
& $paos cat join $room --home $peer
& $paos cat members $room
$msg = 'topic-' + [guid]::NewGuid().ToString('N')
& $paos cat send $room --from $me --body '请在本房间补充各自掌握的条件。' --message-id $msg
~~~

从回执或 `cat read` 取得发言 ID 和序号。接话时加 `--reply-to $msg`；只留公开记录时加 `--no-notify`。以下操作分别在需要读新增、转旁听或正式结束讨论时执行。

- 读发言：`& $paos cat read $room --after 0`，之后用上次读到的 seq 取增量。
- 转旁听：`& $paos cat seat $room --home $me --state observer`。
- 结局后关房：`& $paos cat close $room`，历史仍可读。

### 从 Libraries 找方法，从 EXM 找经历

~~~powershell
& $paos --json library search '录音' --kind workflow --limit 3
& $paos --json library search 'feishu-cli' --kind skill --limit 3
$tools = & $paos --json library tools | ConvertFrom-Json
$tools.raw_markdown -split '\r?\n' | Select-String -SimpleMatch 'lark-cli'
~~~

读命中项的 `source_path`，用原件里的步骤。工具目录支持整页读取，可在输出中筛选工具名。要找本项目已确认的 Tips，用 `& $paos project experience $project`。

从项目 AGENTS 的「共同经历」进入本机 EXM 方法，取得检索脚本路径。REMO 的脚本在本机 PAOE 根目录下的 `Data/exm/exm.ps1`，其余机器按各自的登记填写。

~~~powershell
$exm = '<从本机 EXM 方法取得的完整脚本路径>'
& $exm search '充电站' -n 5 --format json                 # 名称或术语已知
& $exm query '少量抽样导致遗漏长录音中的产品讨论' --no-rerank -n 8 --format json
& $exm get 'qmd://exm/Daily/2026-10-19.md' --full-path  # 换成所选结果的 file
~~~

先读事件原文和后续纠偏，再决定其适用范围。例中，10 月 19 日的记录解释了为什么要覆盖完整时段再判断是否有业务讨论。

## 其他操作与专项说明

| 目的 | 入口 |
| --- | --- |
| 命令环境：PowerShell中文输出 | [UTF-8文本环境](guide-tool-pitfalls.md#powershell-utf-8)，与CLI放在同一段调用 |
| Codex 本人复工 | 从原 Desktop 运行 `orient <project> <本人Sxxx> --resume`，同时恢复本人接收器和读取 AGENTS、INDEX、ENTRY、TODO。Rooter 用 `attention rooter-show --resume`。见[上线准备](guide-paos-cat-operations.md#codex-目标上线准备) |
| 读取恢复原文 | `orient <project> <本人Sxxx> --read` 读取现行 AGENTS、INDEX、ENTRY、TODO，再读本轮原输入。仅查摘要时省略 `--read` |
| 找 Workflow、Skill、Tool 或项目经验 | [工作入口·按需寻找资源](guide-work-method.md#按需寻找资源) |
| 找同事、咨询或交付 | [联系同事与 Rooter](#联系同事与-rooter) |
| 读待处理输入 | `inbox <project> <本人Sxxx>` / `mail list/read` |
| 记录本人已读 | 实读后用 `attention read <project> <本人Sxxx> <notice>`；Rooter 用 `attention rooter-read <notice>`。标读不代替处理输入或完成任务 |
| 接手与更新 | `attention takeover` / `todo-update` / `todo-write` / `handle`；[当前页与输入](guide-paos-cat-operations.md#当前页与输入) |
| 生成本人公开联系包 | [工位Contact薄入口](guide-paos-cat-operations.md#工位-contact-薄入口)：创建CONTACT.md、contact.py、STATUS.md；保留已有文件 |
| 查联系或原消息结果 | `status <project> <本人Sxxx>` / `wake status <project> <本人Sxxx>`；已发信使用 `status ... --message-id <原ID>` |
| 加入已有项目、创建新工位 | [项目和工位创建](../Project-Template/README.md#新项目和工位的创建) |
| 配置本人唤醒器 | [入职与唤醒器](../Project-Template/Workstations/_workstation/notices/README.md#配置与启动) |
| 项目定位 / 首次登记 | `project show` / `project register --root --coordinator`；不创建项目管理状态 |
| 安装定位或库路径异常 | `install show` / `library roots show` / `health`；[Rooter 安装](guide-rooter-installation.md) |
| 对话、日会、Tips 归位 | 日常输入整理（`<workflow_root>/Workflows/wf-meeting-audio-package.md`） |

## 联系同事与 Rooter

项目成员先用 `paos peers <本人项目ID> <本人Sxxx>` 找已登记同事；职责/专长来自项目 `TEAM.md` 的现行成员小节，CLI 未识别时直接打开其 `team_source.path`。返回值的 `installation_support` 单独列出安装级 Rooter（如已登记）；Rooter 不属于 Project 成员，也不需要创建 rooter 项目。联系人读面不探测在线状态，无法证明对方已接手。

项目 Agent 向已登记 Rooter 提交一个需要接续的新请求，使用已有高层入口：

```sh
paos agent send <本人项目ID> --to <Rooter Sxxx> --sender-kind agent --sender-id <本人Sxxx> --subject "安装协助" --body @<UTF-8短请求文件> --message-id <本次唯一ASCII标识> --remind
```

这里第一个位置参数是本次发送的项目上下文，不是 Rooter 的项目 ID。目标由安装登记解析；不要改成 `mail send rooter`，也不要直接往猜测的 Rooter mailbox 写文件。普通项目 Agent 联系其他已登记同事（包括跨项目）仍用 `agent send <本人项目ID> --to <目标Sxxx>`，不把目标项目 ID 填在第一个位置；发现目标不在当前 TEAM 时，通过已知项目或 Coordinator 取得准确员工号，不遍历其他项目库。完整参数使用同版 `agent send --help`。

只检查 Rooter 的联系配置可用 `paos wake status rooter <Rooter Sxxx>`：此处 `rooter` 是现有 wake 命令的位置参数，目标实际沿安装级 Home 解析，不表示要登记一个 rooter 项目。`attention rooter-show` 等命令是 Rooter 当前页读写入口，不是向它发送任务的替代命令。

需要接续的新交付带 `--remind`。已有 Mail 只补提醒时不重发信件；沿 [操作指南](guide-paos-cat-operations.md#联系并让对方接续)核原 message_id 与本次提醒结果。Mail 落盘、提醒受理、实际接手和工作完成分别成立。未登记、STOP、明确失败和结果未知按回执处理，不通过换通道或循环重试掩盖问题。

对方职责不清时找 Coordinator；安装或原生接收问题找 Rooter；具体专业问题可以直接咨询相应同事。请求写清问题、必要原件和期望结果，工作行为与回到主线的规则见 当前项目 `AGENTS.md` 的公共运行区。

命令用途与已退出入口见 [接口参考](guide-paos-interface-reference.md)。详细投递和提醒语义仍由 [操作指南](guide-paos-cat-operations.md)维护；不要在工位另抄一套。

## 外部 Agent 临时协作

已获Human授权在本机执行命令、但尚无员工Home的Agent，可以使用本机已安装CLI持久留信。发送上下文选本次获准工作的Project，接收者从PROJECTS取得已登记员工号；`external`说明外部来源，`sender-id`使用本次真实会话的稳定标识，不表示已入职。

```text
paos agent send <本次获准工作的项目ID> --to <接收者Sxxx> --sender-kind external --sender-id external-codex-<真实会话ID> --subject "具体问题" --body @<请求原文绝对路径> --message-id <本次唯一ASCII标识> --remind
```

这条本机CLI沿现有安装保存Mail/Notice，并可提醒原会话；它与CONTACT面向已登记外部程序的`send --caller`是不同入口。后者按其caller/token合同使用，不能从工位文件索取或复制凭据来替代配置。

外部来源标签不自动产生收件工位。请求中约定一份已有授权目录内的回复文件，接收者处理后写回，外部Agent读原件继续；没有Home时不宣称已建立自动反向Mail/唤醒。需要持续收件与双向接续，就由Coordinator和Rooter沿[现有入职流程](../Project-Template/README.md#新项目和工位的创建)登记这个真实会话。

只提醒读取已存在原件时，也可直接使用[PROJECTS的外部唤醒命令](../PROJECTS.md#外部唤醒)，写清原件和期望回复位置；`wake`本身不创建Mail。不要为补提醒重发正文；回执未知先查原件与处理结果。
