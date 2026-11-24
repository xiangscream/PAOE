---
schema: paos-workflow/v1
id: guide-paos-cat-operations
title: PAOS 操作指南：联系、当前页与运行
description: 按需操作：正常留信与提醒、维护本人当前页、查看版本和排查阻碍。
tags: paos, cat, cli, operations
status: active
version: 101
---

# PAOS 操作指南

<!-- paoe:human-intro:start -->
> [!info] 给使用者
> 这是一份日常操作手册。需要给成员发工作、查看处理情况或排查联系问题时，可以在这里找到具体步骤。
>
> **从这里开始：** 按下面的适用范围和步骤使用；需要执行时让 Agent 从“操作与参考”继续。
<!-- paoe:human-intro:end -->

<!-- paoe:agent-reference -->
## 操作与参考
<!-- paoe:reading-header:end -->

从本人固定 ENTRY 的代码块取得**当前机器实际的 CLI 调用前缀**（包括显式安装文件和方法库配置）；以下 `paos` 只是这个前缀的简写，不应假定当前系统已有同名全局别名。Portable 的 `health` 检查本地安装，`status` 读取工位与联系结果，`install show` 定位安装；不依赖旧 Core HTTP。参数不清楚时直接查对应子命令的 `--help`。

## 查看当前事实

| 目的 | 命令 |
| --- | --- |
| 找回本人的当前责任 | `paos orient <project> <本人Sxxx>` |
| 读分源输入 | `paos inbox <project> <本人Sxxx>` |
| 找同事 | `paos peers <project> <本人Sxxx>` |
| 查看消息与运行状态 | `paos status <project> <本人Sxxx>` |
| 查看已发信件 | `paos status <project> <本人Sxxx> --message-id <id>` |

Mail、正式 Requests 和已配置 CAT 分开读取。读取失败不是零消息；没有配置 CAT 就按不适用处理。

## 联系并让对方接续

需要同事接续时，用 `agent send <本人项目ID> --to <目标Sxxx> --remind`：员工号按本机安装登记定位到 `Workstations/Sxxx`，保存 Mail 与 Notice、沿目标 Contact 提醒一次；Rooter 沿其安装级工位接收。旧项目式 ID 保留在历史来源中，正常交接不继续使用。第一个项目参数是发送上下文，不是目标所属 Project；因此项目同事、跨项目同事、安装级 Rooter 均用已有接口，不另建项目。先从本人 Current 取得成果原件，再编写简短 UTF-8 交接正文，说明结论、接续动作和原件的实际路径；正文用 `@` 读取文件，例如 `--body '@完整UTF-8文件路径'`。Windows批处理入口的多行正文使用该文件方式；内联多行可能在批处理转发时丢失正文和后续参数。

普通交接保存成果后，用 `agent send --remind` 交付、`attention todo-update` 校准本人当前页；下游回告后直接读其成果并继续。解除等待的验收回告也属于需要接续的交付。对方没有回流或报告失败时，再用 `status --message-id` 定位。已有原件和回告即可引用，无须另写一份收件证明或逐级重查全部状态。记录完成状态或回告时，把当前结论写在前，再接续动作和原件。

### 邮件接手、TODO 联动与提醒边界

- **先接手再交付**：收件人实读原信后，只要满足① 职责归本人（对照 TEAM）、② 交付物与落盘位置清楚、③ 起步的核心输入可读，即使局部边界还有模糊或当场就能办完，也应先安静接手。接手静默且幂等，优先把原信关联进本人已有 Task（省略 `--task` 时按 `--title` 新建 Task）；**Mail 与本人 Task 关联即向发件人显示「已接手」**，**个人 Current 始终由本人按当前优先级自行管理**（立即处理时同步切 Current，暂排后面的责任留在 Tasks 中）。
- **发件人任务视图与解除等待**：发件人用 `mail track` 把已发原信挂到本人已有 Task 后，可用 `mail task-status` 和 `mail status` 随时查看投递、接手与结果回执。发件人任务视图直接从对应原信的收件回执解除该项等待，不自动覆盖双方手动 Current。
- **提醒边界与简明唤醒文案（PAOE 0.1）**：接手（`claim` / `rooter-claim`）与普通进展保持静默，不打断发件人。仅在**需要对方回答（范围局部含糊先查 EXM，仍影响动笔再提具体问题并记 `Waiting`）、明确接不了（职责不符或缺失核心前提）、或交付结果需下游接续**时，使用 `agent send --remind` 定向提醒一次。发件人标题应写清业务含义（避免只剩内部代号）；原生唤醒注入词由系统复用现有字段直接拼装（不临时调模型润色），先说清“谁发来什么、下一步做什么”，原信/房间编号退到末行，不堆砌“durable mail”“原输入合同”“本提醒只是……”等内部术语与防御性声明：
  - **Mail 通用模板**（复用 `sender_id`、`subject`、`message_id`）：
    > 收到 `{sender_id}` 发来的新消息：`{subject}`<br>
    > 请读原信，接着处理。<br>
    > （原信：`{message_id}`）
  - **CAT / 角色卡提醒**：`{sender_id} 在讨论房「{room_title}」发来新消息，请查看并按需回应。（房间：{room_id} · 消息：{message_id}）`；角色卡更新用 `Human 更新了你在「{room_title}」的角色卡，请在继续本房任务前查看最新安排。（房间：{room_id}）`。
  - **普通交付收口**：普通交付后发件人解除相应等待即可，省去礼节性回一封「收到」。

| 角色与目的 | 命令（以同版 `--help` 为准） |
| --- | --- |
| 项目成员安静接手 | `paos mail claim <project> <本人Sxxx> <message_id> [--task <已有TaskID>] [--title "<新Task标题>"]` |
| 项目成员写回交付结果 | `paos mail result <project> <本人Sxxx> <message_id> --result "<结果或@FILE>" [--task <TaskID>] [--artifact-ref <成果路径>]` |
| Rooter 安静接手 | `paos mail rooter-claim <message_id> [--task <已有TaskID>] [--title "<新Task标题>"]` |
| Rooter 写回交付结果 | `paos mail rooter-result <message_id> --result "<结果或@FILE>" [--task <TaskID>] [--artifact-ref <成果路径>]` |
| 发件人将原信挂入己方 Task | `paos mail track <project> <发件人Sxxx> <message_id> --task <已有TaskID>` |
| 发件人查己方 Task 在途/回执 | `paos mail task-status <project> <发件人Sxxx> <TaskID>` |
| 查单封原信投递、接手与结果 | `paos mail status <project> <message_id>`（Rooter 亦沿发信上下文 `<project>` 与 `<message_id>` 查询） |

- **真实例子**：S035 发出任务信请 S070 主笔协作规则，S070 实读后先安静接手并挂入本人 Task（未打断 S035 手头工作）；改稿并回读验证后记录交付结果，再通过带提醒交接一次交清原件路径与主要修改点给 S035 验收。

短正文示例：

```markdown
# 交付接续

结论：本次候选已通过受影响检查，结论与边界见原件。
接续：请阅读原件并推进其中明确的下一步。
原件：<本次成果原件的实际绝对路径>
```

以下 `paos` 表示本人 ENTRY 的完整 CLI 调用前缀，`request.md` 是已保存的短交接文件；参数与目标 ID 由当前任务决定，不复制示例占位符直接执行：

```sh
paos agent send 3002 --to S010 --sender-kind agent --sender-id S032 --subject "交付接续" --body @request.md --message-id handoff-unique-001 --remind
```

安装级问题改为 `--to S035`（Rooter）；跨项目仍保持第一个位置参数为发件人项目。若只是简短咨询，不必为了套模板专门创建交接报告或第二份任务。相关联系人与入口见 [操作入口](ops-entry.md#联系同事与-rooter)。

读取投递和提醒各自的结果。需要下游接续的正式交付，将该次完整回执保存在既有任务成果旁；保留目标、时间、message_id和提醒结果，不只截取delivered或next_action。留信成功不等于对方被提醒；原生受理不等于业务完成，最终看对方实际读取与产物。需要接续的新交付使用首次提醒，即使对方正在工作；省略 `--remind` 仅用于不要求接续的留档告知。相同 message-id 的高层重放保留已完成提醒，不再第二次注入；正文或目标改变时是新输入，使用新标识。

OpenCode 正在工作也可以受理新的交付；accepted 时不因 busy 重试。manual_required、native_rejected、离线或 STOP 按回执处理，并保留原件、所需结果和接续人；不循环发送同一输入。delivery_uncertain / network_unconfirmed 表示原生回执未知，accepted 为 null，不得重发或失败后换路。已送达或结果不明时先核原消息状态。

| 失败类别 | 事实与边界 | 下一动作 |
| --- | --- | --- |
| `receiver_stale_registration` | 目标登记的接收进程不存在；Mail 可已落盘，但本次提醒明确未受理。 | 普通发送者按回执交 `repair_owner`/目标本人处理，不查凭据/PID、不代启、不自动重投；安装维护者可沿正常维护入口排查。恢复后按原 message_id 与原文正常接续。 |
| `receiver_offline` | 本次提醒未接通；可能是连接拒绝、目标离线等原因，不能仅凭此断言是死 PID。 | 保留 Mail；交目标本人或回执的 `repair_owner` 核查正常入口。恢复后按原信接续，不自动重投。 |
| `receiver_not_registered` / `receiver_not_prepared` | 当前发送所需的目标侧扩展/准备入口缺失；只说明本次发送入口不足，不是所有 Runtime 都不支持原生提醒。 | 保留 Mail；交目标配置或准备正常入口。有可用的既有正式入口再按原信接续。 |
| `attach_undefined_for_driver` | 人工 attach/navigation 未定义；出自联系读面，不是一次原生发送失败。Codex 也可能返回该字段。 | 不据此判该 Runtime 无法原生提醒；改看实际提醒回执与接收状态。 |
| `native_unavailable` 且 `phase=status_read` | 原生状态读取未成功，本次提醒明确未受理；`prepared` 只证明接收器就绪。 | 保留已到 Mail，交原Owner/Rooter核原会话错误。容量失败沿原Home/Thread的已有恢复入口接续，配置沿当前授权；恢复后读原信，不因503重建接收器或重投业务。 |
| `delivery_uncertain` / `network_unconfirmed` | **提醒结果未知，`accepted=null`**；Mail 是否已落盘按 delivery 回执独立判断，不能因提醒未知就写 Mail 未确认。 | 先核原消息/delivery 回执与 reminder 记录；不重发、不换通道、不改身份。 |
| `native_busy` / `native_rejected` / STOP / 明确离线 | 本次提醒被明确拒绝或停止；不等于 Mail 未保存。 | 按回执的 `repair_owner` / `next_action` 处理；不循环重试。 |
| Mail delivered / reminder accepted | 只证明保存与本次受理，不等于同事已读取、已处理或业务已完成。 | 等实际读取/产物；需要接续时按原信继续，不重复发送。 |

Codex的`wake status <project> <本人Sxxx>`与`status`使用同一Contact事实：`receiver.state=process_not_running`表示登记进程已退出；`process_identity_mismatch`表示同号PID已不是原receiver实例，即使pid_alive=true也不是prepared。prepared须核OS实例，不等于原生可用或业务消费。一次提醒明确区分receiver_offline/receiver_not_prepared、native_busy、native_stopped及delivery_uncertain，回执附error_code、repair_owner和next_action。状态未确认仍是unknown；调用方不再自己读登记、查PID/端口或重置绑定。

`attach`描述人工打开或接入Runtime的方式。已配置 native target 的 `binding_status=configured` 只表示目标存在，不等于 bound、online 或已消费；未配置仍为 `unbound`。`attach_undefined_for_driver` 不能单独说明原生提醒不可用；应看该驱动的接收状态及具体提醒回执。Codex 保留其 Desktop/thread 人工导航；其它 Runtime 显示自身已配置的 `manual_open` 或诚实未知，不套用 Codex 路径。Codex读`receiver.prepared/pid_alive`；WorkBuddy还需其已授权扩展实际运行。

Codex正常接收器对明确active/idle/notLoaded向既有原生跟进入口提交一次已授权短Notice；不因active预先拒绝，不覆盖模型或Follow-up设置。回执的`native_status_before_submit`只表示提交前观察，不保证steer、下一turn排队或业务消费。未知、STOP和实例核验保持。若入口明确返回`native_busy / accepted=false`，按真实拒绝处理；不要在active回合内等待自己被唤醒，也不自动重投旧输入。

WorkBuddy回环建立连接前明确被拒绝为`receiver_offline / accepted=false`；SDK调用后的错误、超时/复位和响应丢失仍保留结果未知。旧回执不改写、不补投，产品支持的正式安装与授权阻碍独立保留。

已留信但尚未提醒的旧输入，用原件补 `wake trigger` 一次；不要为补提醒重发原信。参数看安装 help。

接收者结束回合前读当前相关 pending；有可执行输入就继续。具体等待和收口按 当前项目 `AGENTS.md` 的公共运行区，不把早期 inbox 为空当成收尾时仍未收到。

S号寻址和跨Project参数查安装 `agent send --help`。普通消息使用现有Contact，不用 native UUID、同事凭据或另建服务。

### Codex 目标上线准备

正式入职或换Runtime时，通过正常 `wake bind` 一次补完整Contact。恢复沿原Home、Thread、模型和STOP，不重复绑定或复制同事凭据；配置缺项按同版帮助修准确登记。

已配置 Codex 接收器的本人从原 Desktop 复工时，使用安装 CLI 的 `paos orient <project> <本人Sxxx> --resume`。安装级 Rooter 使用 `paos attention rooter-show --resume`。复工同时读取本人原件并准备接收器。只单独准备时，仍用 `paos wake prepare-current`。`receiver_preparation` 回告准备是否启动、复用或受阻。`paos wake status` 可核实际就绪，实际接续看本人读信。`orient --read` 和 `contact.py prepare` 供只读查询。

正常准备会核本人进程实例、已鉴权接收器和其实际捕获的Desktop连接。同一有效连接复用；宿主连接已更换时，沿已确认本人的恢复路径处理。缺原环境、连接证明未知、外Thread或STOP按准确错误保留。失败只报告具体断点，不换身份或自动重试。

安装人可将同版 `scripts/codex_receiver_session_start.py` 接到 SessionStart startup/resume 和 UserPromptSubmit，按宿主入口审阅。登记的 Hook 到达 Python 后，接收器生命周期日志中的 `owner_hook_entered` 记录事件以及本人 Thread、连接环境是否可用。SessionStart 缺少 Desktop 环境时，Hook 提示本会话在原工具环境走复工入口。宿主加载事件决定 Hook 是否执行，云编排只支持其管理的 Global MCP Hook。 [Codex Hooks](https://learn.chatgpt.com/docs/hooks#hooks-with-cloud-orchestration)

旧接收器缺本版连接证明，或需要载入新接收行为时，本人从安装Source的scripts目录执行 `python -X utf8 -B codex_receiver_session_start.py --update-current`；它只管理已核本人的原实例，保留原locator与STOP。正常复工不反复重载健康实例，也不因Source其它模块升级而重启所有接收器。

普通发送仍用 `agent send --remind`，调用方不用查pipe、PID、端口或替同事启动服务。Desktop离线时保留持久消息并报告不可达，不自动启动Harness、不重放旧请求。Windows/WSL调用沿登记的正常入口，不在失败后改走另一条路。

精确启动、连接比对、旧实例处理和退出记录读当前安装的 `source_root/docs/CODEX-SELF-REMINDER.md`；Source定位取 `paos install show`，不沿旧电脑路径读取。实际接续按当前项目AGENTS处理。

## CAT 圆桌

网页入口、轻量JSON与实时显示的功能说明见 [CAT](../CAT/README.md)；启动方式沿现有System网页入口，不另建消息服务。本节是 CAT 讨论、任务房与在线协作的唯一操作细则（具体参数以同版 `--help` 为准）。

CAT是系统级公共讨论入口，可跨Project；重要结论回原Project。Room与同事从现行Project/联系入口取得。

单点事实或二选一授权（答案只在发件人一人手里）沿原信带 `--remind` 一次问清即可。涉及**三方及以上角色对焦**，或**方案开放、一方回答会立刻改变另一方拆解与措辞**（如长程共写、碰撞场景或解决分歧）时，任何参与者都可主动发起 CAT，优先复用同题房间，使用已登记 S号入座。形成行动或决定后回本人 TODO 和项目正文，正式交接用 Mail。

### 任务房、负责人与关房边界

- **专用目标房与共享讨论房的关房区别**：
  - **目标专用房（为单一目标单独建立且唯一关联该目标）**：登记目标、负责人已有 Task/计划关联、共同口径（`--project-id`、`--index-path`，直接复用 `Works/` 既有页面）与验收负责人。房间持续开放，即使成员全部离线也继续保留；当约定验收人读到最新 Human 房内输入、明确交付与剩余事项去向并通过验收后，由系统自动关闭（沿 `task accept` 完成；Human 保留的验收仍由 Human 确认）。
  - **共享讨论房 / Agent 小房（`--close-policy owner`）**：承载多项议题的共享房或 Agent 自行发起的小房，不被单一目标验收自动关闭，由负责人或发起人在结论归位后正常关闭；关闭后历史可读。
  - **Human 手动关房（`--close-policy human_confirm`）**：如仍显式指定需 Human 手动关房，沿既有 `cat close --action request|confirm|continue` 执行。
- **房间 INDEX 与负责人**：任务房负责人沿 [Coordinator 工作循环](wf-coordinator-governance-cycle.md#4-项目口径收口与阶段归并) 维护任务 INDEX（目标与交付、Human 当前要求、待定问题、下一步与负责人）；任务结束后稳定结论归入项目 INDEX 或成果原件。

### 0 类综合工作与临时角色卡（PAOE 0.1）

- **两次 Human 放行**：Human 以 `0` 开头的真实新输入（不从引用、正文或历史消息触发）由临时负责人按四步推进：① 拟团队计划（仅登记规划责任）→ ② **Human 第一次放行**后建本目标专用 CAT 并邀请同事 → ③ 成员在房内完善临时角色卡（放行前拟职责与拟 TODO 安排仅存房间/计划原件，不提前写入正式执行 Task）→ ④ **Human 第二次放行**后按已批准版本接入本人正式执行 Task 并全员开工。普通非 0 类任务按原授权直接执行。
- **临时角色卡**：每张卡对应一名已有员工（姓名/员工号、Harness、本轮临时职责、本轮 TODO 安排、协作关系与成果链接），放行后直接从本人 Task 与业务原件投影，不另抄第二份进度。Human 保存修改后系统直接提醒对应成员，继续该房任务时在下一次请求或动作边界带入变化（不波及无关任务、不增加手动确认），负责人后续汇总同步即可。Agent 在原授权内更新进展照常进行，仅实质改动已批准的目标、参与人、职责或交付范围时交受影响差异。

### 在线循环、离线语义与恢复扫房

- **高频在线（`presence=online`）与后台作业分离**：**CAT 在线仅表示本人承诺会主动回看本房**，不按接收器进程猜测，也不把“仍有后台命令或子任务在跑”写成 CAT 在线（后台作业状态另行附带显示）。高频在线者每做完一个可交付的小步骤、准备开始下一步时，主动回房看新增，实读后用 `cat progress --read-to <seq>` 显式推进游标（`cat read` 不自动推进游标，游标不回退且不超当前 `last_seq`）。
- **离线不是离席（`presence=offline` ≠ `left`）**：停止本轮工作循环或不再主动看房时，主动将本房状态记为 `offline`（阶段停止不取消后台作业）。**不要把 `offline` 写成离席（`left`）**——离线仍保留成员席位（`participant`）、任务与已读位置，仍可被点名或 Human 全房提醒唤醒；状态无法确认时记 `unknown`。
- **恢复先扫房**：新会话、接班、压缩恢复或被唤醒时，先用 `cat list --home <本人Sxxx>` 扫自己仍承担责任的相关房间与未读数（`left` 不进入恢复列表）；再读房间挂载的 INDEX、临时角色卡变化与上次已读位置之后的未读增量（`cat read --after <last_read_seq>`），核对是否有 Human 新要求，实读后显式推进游标并恢复 `online`。

### 发言提醒、多选点名与命令速查

| 目的 | 命令（以同版 `--help` 为准） |
| --- | --- |
| 扫本人负责房间与未读增量 | `paos cat list --home <本人Sxxx>` |
| 创建任务房 / 小房 | `paos cat create --title "<标题>" [--from <actor>] [--owner <owner>] [--close-policy human_confirm\|owner] [--goal "..."] [--source-ref <路径>] [--human-request-ref <来源>] [--project-id <id>] [--index-path <相对路径>]` |
| 首次入席（建房后先入席再发言/推游标） | `paos cat join <room> --home <本人Sxxx> [--label "<标签>"]` |
| 更新房间任务与 INDEX 引用 | `paos cat context <room> --from <actor> [--owner <owner>] [--goal "..."] [--project-id <id>] [--index-path <相对路径>]` |
| 看房间概况 / 成员与在线状态 | `paos cat show <room>` / `paos cat members <room>` |
| 读未读增量 | `paos cat read <room> --after <已读seq>` |
| 记录在线/离线并推进已读游标 | `paos cat progress <room> --home <本人Sxxx> [--presence online\|offline\|unknown] [--read-to <seq>]` |
| 预览本次实际提醒对象 | `paos cat preview <room> --from <sender> [--mention <Sxxx> ...] [--invite]` |
| Agent 静默发言（默认） | `paos cat send <room> --from <本人Sxxx> --body "<内容或@原件>" --message-id <id>` |
| 邀请一位同事入席并提醒一次 | `paos cat invite <room> --from <本人Sxxx> --to <目标Sxxx> --body "<具体问题与背景>" --message-id <id>` |
| 点名一位或多位在席同事回应 | `paos cat send <room> --from <本人Sxxx> --mention <Sxxx> [--mention <Sxxx>] --body "<具体问题>" --message-id <id>` |
| 显式群提醒桌内参与者 | `paos cat send <room> --from <本人Sxxx> --notify --body "<内容>" --message-id <id>` |
| 调整本人席位 | `paos cat seat <room> --home <本人Sxxx> --state participant/observer/left` |
| 提请 / 确认 / 继续关房 | `paos cat close <room> [--from <actor>] [--action request\|confirm\|continue]` |

- **Human 与 Agent 提醒边界**：Human 不点名时提醒本房任务组全员，包括在线、离线和状态未知的成员。明确选人时只提醒所选成员。成员名册和发送预览把主动旁听者单列为「旁听，不在任务组」；Agent 普通发言默认静默，需回应时用 `--mention <Sxxx>`（可重复选多人，接话加 `--reply-to <原消息id>`，离线成员也可被点名唤醒）。`--notify` 与 `--mention`、`--no-notify` 互斥，显式群提醒由 Human 主动选择。发前可用 `cat preview` 核对同一后台计算的收件人。
- **幂等、席位与收口**：相同 `--message-id` 原样重放只存一次、不重复唤醒；改目标或提醒方式报冲突。`participant` 接提醒并可发言；`observer` 只读、不接提醒（不因在线恢复提醒）；`left` 退出席位、不进入恢复列表，历史保留。不发空 ACK、不反复自唤醒或把讨论逐句复制到 Mail；正式交付仍沿 Mail/Contact 一次完成。
- **真实例子（CAT 主动共写）**：S035、S069 与 S070 在同题房 `room-234350df7e6a` 共推协作规则：S070 静默贴出初稿进展，S035 给出收敛意见并点名 S070；S070 收紧正文后在房内定向点名 S069 追问“局部模糊先接手还是先提问”，S069 结合真实任务给出三项接手条件与开 CAT 分界，S070 一次落回原稿并交回 S035 验收，全程无多余群打断。

show默认只返回房间概况、人数、消息数与last_seq，普通与JSON读面相同；成员读members，新增发言读read --after。确需完整历史时显式用`paos --full-result cat show <room>`，整史不作为每次恢复输入。

## 当前页与输入

| 目的 | 安装入口 |
| --- | --- |
| 读本人 TODO 与 Notice | `paos attention show <project> <本人Sxxx>` |
| 改本人 Current 字段 | `paos attention todo-update <project> <本人Sxxx> --set 'objective=当前目标' --set 'next_action=下一步'` |
| 更新 Tasks 或恢复完整 TODO | `paos attention todo-write <project> <本人Sxxx> --body @<候选载荷文件>` |
| 处理输入 | `paos attention handle <project> <本人Sxxx> <notice> --resolution "处理结果" --action-ref <任务或成果>` |
| 展示归档 | `paos attention notice-update <project> <本人Sxxx> <notice> --archive` |
| 登记已落盘的直接输入 | `paos attention source-register <project> <本人Sxxx> --source-ref <绝对路径或URL> --summary "索引"` |
| 核已存在的输入 | `paos attention source-status --help` |
| Rooter Home | `paos attention rooter-show`；同组 `rooter-*` 子命令维护自己的输入和 TODO |

普通 Current 维护用 `todo-update --set 字段=值`，只改提交字段，保留原元数据、未提交字段与 Tasks。列表字段 `result_refs/context_refs` 按重复 `--set` 收集，替换该列表；字段全集查同版 help。核写入回执中的实际 Current 和任务数即可，不要求另建整份候选或再次调用orient。接班定位或写入结果异常时，再用orient读取当前事实。

### Notice 登记与合并读面

Notice 的 Markdown 文件只是输入登记；当前 `state`、`read`、`archived` 以官方合并读面为准。Project 读 `attention show` 的 Home 服务结果，Rooter 读 `attention rooter-show`；工具和脚本复用同一官方读取，不只扫 `notices/*.md`，也不只合并某一个 `.read`/`.handled` sidecar 就推断状态。原 Mail/登记保留；处理仍用 `attention handle`，展示归档用 `notice-update`。

历史积压按已有证据处置：已有完成或取代证据的补收口；仍需行动的进入本人 Current；来源缺失或业务未定的保留具体 Owner。阶段接受不等于同日期所有业务完成；不按年龄清空、不伪造逐封 read、不重执旧授权。普通 Owner 维护自己的工位。

### 已处理输入的库外归档

System 0.2.2 提供 Project 工位与安装级 Rooter 的物理归档操作，历史 Mail 的处理状态与关联 Notice 一致。Owner 先核官方读面中的已读和 handled 状态，选定没有当前依赖的输入，再执行：

```text
paos attention archive-input <project> <agent> --message-id <原消息ID> --history-root <库外绝对批次>
paos attention archive-input <project> <agent> --notice-id <独立Notice的ID> --history-root <库外绝对批次>
paos attention history-read --history-root <同批次> --agent-id <agent> --message-id <原消息ID>
```

安装级 Rooter 使用本人入口，默认沿 installation 定位 `rooter-001`，无需 Project：

```text
paos attention rooter-archive-input --message-id <原消息ID> --history-root <库外绝对批次>
paos attention rooter-history-read --history-root <同批次> --message-id <原消息ID>
```

Rooter 的独立 Notice 同样用 `--notice-id`；沿原 Home 与原标记定位，不创建临时 Project 或新身份。

旧的无frontmatter Mail，`--message-id`使用磁盘实际原文件名（可含中文和`.md`），同名用于`history-read`，后者不带Project/Agent位置参数。交接名单取实际目录；完成回报给准确批次、处理状态及原始读回路径，不手抄正文标作原件。

多条已确认的历史输入，可在同一次执行中循环现有接口，例如每批20条，无需逐条发起对话或先等新命令。首批用`history-read`读回处理状态与实际归档位置，一致后继续同类余件；具体异常保留源件和首个断点。当前任务、未完责任与在途操作仍依赖的输入继续保留。

Mail 与关联 Notice 一起归档；独立 Notice 用 `--notice-id`，历史读回时也用同一参数。批次保留原目录结构和处理事实，项目 HISTORY 链接该批次。`history-read` 必须给准确批次，不会按 ID 全局搜索历史；展示归档仍只改变当前视图。

成功归档后，同一 message-id 不重建历史件或重复提醒；从未送达的目标仍可按原投递合同补齐。文件移动与归档标记分步完成：中断时先核错误中的进度、源路径和原批次，完成收尾前不要重放发送。完成后读回历史正文与 Mail/Notice 处理状态，并确认对应原件已退出活跃目录。

Rooter Current 使用 `paos attention rooter-todo-update --set objective=... --set next_action=...`，沿登记 Home 复用同一字段合同；`--home-id` 默认 `rooter-001`。

现行 TODO 为 `paos-todo/v4`，Current 仅含 `objective`、`next_action`、`waiting`、`inflight`、`context_refs`、`result_refs`、`updated_at`；目标和输入引用可在同一次 `todo-update` 中用多个 `--set` 更新。

已发布字段合同：`updated_at` 属 Current；`todo-update` 与 `rooter-todo-update` 实际改动才刷新它，no-op 不刷新。任务层 `source_refs`（原输入）与 `acceptance_refs`（已接受成果的具体版本）随**完整 `todo-write` 载荷**维护，**不放入 Current**；只写本人当前页，不新增 `task-id`。字段可空，按需维护，不补写全部历史任务或造演示任务；引用存在不等于 PASS，PASS 仍按实际验证。Project 与 Rooter 的 `todo-update`、`todo-write` 都可带 `--expected-fingerprint` 做过期守卫；全量写入前从本人最新 TODO 原始字节取得 SHA-256，失配则回读并重新整理候选。

需要改 Tasks 或恢复破损 TODO 时，在独立候选载荷文件中保留正确元数据和原责任，再经 `todo-write` 写回。按任务ID定位目标条目，写回后核该条目的勾选状态、result和成果引用；不再另写任务 `state` 字段。`trusted` 只说明格式可读，下一步按 Current 引用的项目状态和原件校准。不要先覆盖唯一 TODO 再校验。Notice 的展示归档不代处理，也不删除正文。只写本人当前页；任务完成和历史索引按工作循环归位。

Tasks 引用采用缩进列表，不能把路径写在 `Source refs` 的同一行。例如：

```markdown
- [ ] **T-示例** · 本次行动
  - **Source refs:**
    - Materials/原始输入.md
```

### 明确接手一条输入

Project Home：

```bash
paos attention takeover <project_id> <agent_id> <notice_id> \
  --set objective='本次目标' --set next_action='下一步'
```

Rooter Home：

```bash
paos attention rooter-takeover <notice_id> \
  --set objective='本次目标' --set next_action='下一步'
```

一次显式接手依次做三件事：读取该 Notice 的 Mail 原件；标读该 Notice；只把提交的 `--set` 字段写入本人 Current。未提交的 Current 字段、Tasks、身份、Mail 正文和 Project 状态保持原样。标题和摘要不用于猜任务。

- 这是**字段补丁**，不是替换整份 Current。旧 `waiting/results/...` 只有在本次显式提交对应字段时才变化；撤旧引用直接显式提交空值，如 `--set result_refs=`（现有写者规范为空列表，Tasks 不动），不需要额外 clear 参数。
- 至少提交一个字段；可加 `--expected-fingerprint`，TODO 已变化则整次在写前拒绝。
- 目前只支持能实际读取的 Mail durable 来源；其他来源明确返回 `attention_takeover_source_unsupported`，不冒充已读。
- 坏字段/坏值/缺来源/坏指纹都在标读前拒绝。若来源和标读已成功、Current 写入再失败，回执带 `stages` 说明已完成哪步；从该事实接续，不自动重试。
- 标读不等于处理完成：Notice `handled` 仍需正常 `attention handle`；本入口不触发模型、不唤醒自己、不改模型/STOP。

### 本地工位读面

直接使用 `orient`、`attention show` 和 `inbox`，需要原件时读 TODO/Mail/Notice。
不再重建第二份 Markdown 工作台，也不轮询生成页。读到输入后按实际接手与处理
记录 Notice；已读不等于完成。正常连续阶段只读相关增量，恢复时读 ENTRY、当前
工作和必要原件。接口用途见[Home 读面](guide-paos-interface-reference.md#home-读面)。

### 工位 Contact 薄入口

已登记并初始化的Home使用现有公开包装生成联系包。将下面两处占位值换成本人ENTRY中的安装描述和员工号 Sxxx；从Home、Project或System目录均可执行，不依赖源码工作目录。

```powershell
$contactInstallationFile = '<本人ENTRY中的安装描述绝对路径>'
$contactInstallation = Get-Content -LiteralPath $contactInstallationFile -Raw -Encoding utf8 | ConvertFrom-Json
$contactPackageScript = Join-Path $contactInstallation.source_root 'scripts/paos_contact_package.py'
python -X utf8 -B $contactPackageScript '<本人Sxxx>' --installation-file $contactInstallationFile
```

此命令只创建缺失的公开文件，已有原生绑定和接收器状态保持。

安装函数按“存在则保留、缺失才创建”处理，生成三份薄文件：

- `contact.py`：实际调用入口；
- `CONTACT.md`：联系与恢复说明；
- `STATUS.md`：最小工位导航/状态页。

已有同名文件不覆盖，已有人工内容不因安装而重写。三份文件都只落在准确 Home；Rooter 包不绑定 Project。它们调用安装 Source 中已有共享实现，不复制 driver、token、PID、native credential 或第二套规则。代码候选存在不等于真实 Home 已安装；实际安装、读回和采用仍以安装记录及真实结果为准。

运行 `python <Home>/contact.py status` 读取准确 Home 的共享读面、联系状态与 `capabilities`。`send/notify` 的调用方条件统一读现行调用方授权。正常成员交接使用 `agent send --remind`；薄入口沿用原权限与 Contact/Notice 语义。

`STATUS.md` 只是稳定导航和读面入口，不是第二个 Current/TODO 或验收权威。需要真实事实时回到准确 Home 的 TODO、Notice、原输入、成果及共享 read service；页面显示来源、指纹、观察时点、恢复集合和过滤/缺失范围时，以这些原件为准。

### 显式标读（Notice read）

先读原输入，再显式标读；普通读取与列表本身不改变 read 状态。两个显式入口：

| 目的 | 命令 |
| --- | --- |
| 标读 Project Home 的一条 Notice | `paos attention read <project> <agent> <notice>` |
| 标读 Rooter Home 的一条 Notice | `paos attention rooter-read <notice_id> [--home-id rooter-001]` |

标读只写该 Home 的独立 `.read` sidecar，保留首次 `read_at`；重复调用幂等（`read_changed=false`）。**read 与 handled、接受、业务完成分开**：标读不改 Mail/Notice 正文、不改 handled、也不代表已接受或已完成；处理仍用 `attention handle`。

## 工具权限与模型

Human 已授权本机 OpenCode 全部工具权限。Rooter沿服务正式 Config/Session 接口配置并核有效值；普通工具执行不要求逐次审批。若仍遇工具 ask/拒绝，保留具体错误交 Rooter修运行配置，不建立另一套审批服务。

工具权限不改变业务范围、对外承诺或明确的 Human 验收点。除非 Human 指定，不改原会话模型；正常提醒省略 `--model`，继承当前选择。

Human 显式指定 OpenCode 模型时，`--model` 传完整原生 JSON 对象，例如 `'{"providerID":"opencode-go","modelID":"deepseek-v4.1-flash"}'`；不传 `provider/model` 字符串。其他正常提醒省略该参数，继承原模型。具体参数见安装 `wake trigger --help`。

后台 OpenCode 从已安装版本的正常入口查看原会话。v2使用 `opencode --server <当前服务URL> --session <当前sessionID>`；URL与ID从当前联系事实取得，机器profile沿本机启动入口，不另建替代会话。

按当前安装版本的正式状态读面核目标Session及实际工作目录。旧版HTTP路径和状态作用域不能套到新版；空状态表只说明本次查询结果，不据此判断所有会话闲置或已停止。

维护共享 OpenCode 服务前，核该服务所有已绑定 Agent 及其实际 directory。任何会话仍在运行就保留服务到安全点；不能用一个 directory 的空状态表判断整台 server 空闲。

## 安装与目录

Windows/WSL 共用安装描述，定位看 `paos install show`。已批准的候选直呼需显式安装描述和受控根，参数查同版 help，不复制另一份默认配置。

Library 源文件变化后用 `paos library catalog workflow --root <Workflow根>` 重建目录，保留使用记录。运行切换和回退见 [升级与采用](guide-upgrade-adoption.md)，安装异常见 [Rooter 安装](guide-rooter-installation.md)。

## PAOE 0.1 共用动作速查

以下接口随 System 0.3.0 与配对 CAT 正式发布。本机版本与定位用 `paos install show` 读取，详细参数以当前安装的 `--help` 为准：

| 入口与状态 | 适用时机 | 命令与关键边界 |
| --- | --- | --- |
| `context read` | 会话启动、恢复、压缩后或显式补读 | `paos context read <本人Sxxx> [--task <TaskID>] [--reason startup\|resume\|compact\|stage\|request] [--source <原件>]`；返回原文、版本与缺项，不凭读取就记录请求已装载 |
| `context stop` | 回合停止或中断时处理 CAT 离线与至多一轮纠偏 | `paos context stop <本人Sxxx> --event <宿主事件ID> [--task <TaskID>] [--cat-url <URL>] [--interrupted\|--reentry\|--waiting-human]`；返回 `action=stop\|continue`、`rooms_offline` 等，不作任务验收 |
| `team-plan` | 0 类团队计划、两次放行、角色卡草案与历史回执核验 | `propose <负责人Sxxx> --task <ID> --plan <原件> --member <负责人Sxxx> --member <成员Sxxx> [--close-policy human_confirm\|owner]`（逐人重复 `--member` 且包含负责人；按 `#Scope` 选章批准时将 `Progress` 放独立章节）；`role <本人Sxxx> --room <room> --duty ... --arrangement ... --deliverables ... --expected-revision <rev>`；`enroll <本人Sxxx> --room <room> [--task <ID>]`；`members --room <room>`；`confirm {open-plan\|approve-roles\|save-role\|accept-goal} --id ha-<32位小写hex> --input <JSON\|@file\|->`（`--id` 同一操作幂等复用、不手填放行记录）；历史回执查验用 `receipt <receipt_id> [--verify] [--archived-artifact <归档成果路径>] [--archived-basis <归档依据路径>]`（均可选 `--cat-url`） |
| `stage deliver` | 显式交付一阶段成果 | `paos stage deliver <本人Sxxx> --task <TaskID> --id <稳定交付ID> --artifact <成果路径> --intent <意图来源> --result "<结果>" (--next "<下一步>" \| --waiting "<等待>") [--current] [--cat-url <URL>]`（隔离联调可传 `--cat-url`）；写前核必需原件，成功只返回阶段回执；进入下一阶段时由原生接线或显式 `context read` 取回原文。**默认不结束整项 Task**，且不替代本目标的最终验收（整项完结时，有原 Mail 的任务走 `mail result`，普通 Task 按验收条件收口） |
| `task accept` | 约定验收人完成整项目标验收并关闭专用房 | `paos task accept <验收人Sxxx> --task <TaskID> --artifact <项目内成果文件> --basis <项目内验收依据文件> --remaining "<剩余事项去向>" [--room <room> --read-to <实际已读seq>] [--carry HOME/TASK=continuation] [--cat-url <URL>]`；收口当前明确指向该任务的工位责任，`--artifact`/`--basis` 均指向项目内已有文件；普通 Task 可省 `--room`，专用房须同时给 `--room` 与实际读到的 `--read-to`（首次关房由适配器核验）；`human_confirm` 策略须先由 Human 完成 `accept-goal`，再由负责人收口本人 Task |
| `content changes / consume` | EXM 整理者拉取变化清单并登记消费位置 | `paos content changes [--after <N>] [--limit <N>]`；`paos content consume <本人Sxxx> --through <N> --result-ref <整理结果路径>`；按同一原件版本合并去重，索引失败不回滚正文 |
| `context search / collections` | 新目标或方向调整，按项目/方法/经历三库筛选检索，或只读查看集合注册命令 | `paos context search <本人Sxxx> "<查询>" [--scope project\|methods\|experience]... [--project <项目ID>] [--mode lexical\|semantic\|hybrid] [--limit <N>]`（`--scope` 可重复）；`paos context collections <本人Sxxx> [--project <项目ID>]` 只读给出每一集合的注册命令。缺集合会清楚报告覆盖不足且已有结果仍可读，日期只用原件声明 |
| `content watch` | 整机单一本地内容观察进程 | `paos --installation-file <安装描述> --json content watch`（不传 Home）；启动先订阅目录，再补录停机期间的变化，`ready` 表示两步均已完成，`Ctrl+C` / Windows 控制台 break 协同停止，同安装第二实例明确失败；仅管本地文件（云端原件走既有工具 `read / refresh`），正式登录启用由 Rooter 负责 |

## 问题定位

| 情况 | 下一动作 |
| --- | --- |
| 工位、身份或安装根不符 | 实读 ENTRY/安装描述，交 Rooter修准确入口 |
| 邮件回执与目标文件冲突 | 保留原输出，核同一 message/Notice/目标文件，交公共维护者 |
| 对方无回流 | 核原消息、对方 Notice/Current和产物；有实际消费就保留，不盲重发 |
| 消费端目录或计数停更 | 先查原请求的提醒结果，再读目标接收状态；目录计数仅作线索，登记、进程和接收入口由运行维护者核查 |
| TODO 不可信 | 保留准确字段错误，由本人修当前页；产品代码、公共接口和硬接入由 S010 组织，Rooter 维护软方法及安装运行 |
| 公开联系字段缺失 | 核当前读面，Rooter沿既有授权更正明确字段，不重新入职或新建 Agent |
| 模型额度耗尽 | 保留成果，停止受影响会话的无效重试；Coordinator 用已有授权且可用的执行者接原任务，Rooter 修运行接续；模型、付费和新资源沿 Human 设置 |
| 安装/Library损坏或 CLI参数不认 | `install show`及同版`--help`定位，交对应维护者 |

研究与蒻芷联系方法见 研究与咨询（`<workflow_root>/Guides/guide-research-consultation.md`）。

回报只写实读产物和实际执行结果，表达沿 简明表达规则（`<workflow_root>/Guides/guide-concise-writing.md`）。

## Mail / Contact / Wake 硬通信协议

这里的 protocol 只指传输字段、消息 ID/幂等、`Notice` 读取/处理状态、Contact 绑定和 STOP、唤醒响应与失败码等机器约定。调用先以当前已安装 CLI 的 `--help` 和对应实现/合同为准；本指南描述适用场景与错误恢复，不额外维护第二套消息 schema。CAT 服务未配置时保留明确不可用事实，不拿 Mail 或 Wake 的结果冒充 CAT 在线。
