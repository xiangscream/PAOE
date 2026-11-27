# 铸币程序：显式检查点接续

铸币程序读取原TODO中的安排，由现有 `content watch` 托管，经已有Contact向原会话提醒一次。Task与成果仍由本人维护；程序不替人判业务完成、不拉起离线App，也不依赖各Harness的Stop续工Hook。

## 先有安排，再进入业务

给本人已有Task登记准确时间和业务来源：

```text
paos mint plan S034 --task T-EXAMPLE --id after-claim --on claim --at 2026-11-28T09:00:00+08:00 --source-ref Works/example/BRIEF.md
```

`--on claim|doing|stage` 分别在第一次接手、从其他状态进入doing、首次写入对应新阶段时激活已安排的时间。安排保存在该Task的 `Checkpoints` 列表，含id/on/at/source_ref/armed/cancelled。只有命中接入点才将armed写为true；不猜进度、不凭mtime或固定延迟造时间。应在该次业务入口之前登记计划。新建Mail Task没有预先安排时，接手回执报告 `checkpoint_schedule.state=schedule_missing`；阶段回执也显示是否有stage安排。

已经知道要直接预约一次时，用 `mint arm`，它不要求再进入一次阶段：

```text
paos mint arm S034 --task T-EXAMPLE --id next-morning --at 2026-11-28T09:00:00+08:00 --source-ref Works/example/BRIEF.md
paos mint cancel S034 --task T-EXAMPLE --id next-morning
```

ID在同Task内唯一。改期用取消原点、新建ID，不改已提交或结果不明请求的身份。没有具体安排就没有自动时钟接续；普通保存不会凭空产生检查点。

## 交付和CAT条件

原 `notify_after` 的to/when/source_ref字段保持。只有明确枚举被程序执行：

- `task_done`：来源Task真实done时，通知to指定的登记Home。
- `stage_delivered`：来源Task关联的正式stage交付finished时触发；source_ref可准确指定 `stage:<交付ID>` 或该阶段的成果/意图定位。
- `cat_checkpoint`：source_ref必须是 `cat:<房间ID>#<事件名>`，房间与事件名都匹配才触发。

原有“完成后”等自由文字仍保留，程序不猜它的含义。to与source_ref跟随原条目，不依列表顺序配对。新的明确交付可以提醒正在等它的收件人；程序不替收件人解除waiting。本人定时续工则要求该Task通过共用可执行判断，Task级waiting不挡同表其他责任。

只在需要触发已登记CAT条件时显式发布事件：

```text
paos cat send ROOM --from S034 --body @actual-delivery.md --message-id stable-message-id --checkpoint ready --no-notify
```

这一步仍先走原CAT消息提交，再将准确房间、事件名、原message-id写入已有内容事件日志。普通CAT消息没有此事件；checkpoint与mention/invite/notify互斥。CAT已经保存而本地事件发布失败时，错误可见，使用同一原message-id正常重入补发布；不要改ID重发正文。此入口是CLI显式信号，不宣称所有CAT界面普通发言都已产生检查点。

## 一次执行与暂停

现有SQLite新增 `mint_runs`，主键为target_home/checkpoint_id。提交前先持久保留uncertain占位，返回后分别记submitted、rejected、uncertain或suppressed；这些是投递事实，不是Task状态。相同请求、重启、休眠恢复都不重发submitted/uncertain。进程在提交附近退出时，保留未知占位交原Owner核对。

明确拒绝或抑制保留原TODO和原因，不做60秒盲重试。需要一次新的明确重核时：

```text
paos mint check S034 --request-id owner-check-001
```

同request-id重入不会重投，包括A→B→A交错及进程重启。各次明确检查在同一mint_runs表内保留独立请求行，主检查点仍阻止重发已受理/未知的请求。新的request-id只可重核rejected/suppressed，不能重发submitted/uncertain。原定时责任的真实状态/等待变化、新正式阶段也可重核被拒绝或抑制的检查点；普通改字或重复保存不是新的重核事件。新的独立CAT事件或新预约点可正常接续。

责任转换与显式请求重放分开识别。同表的observed记录保存检查点最近一次可观察责任签名及递增序号，实际观察到doing→waiting→doing会得到新的转换序号；不再把最后状态相同当成同一次事件。序号持久化，重复保存及无变化重启不增加序号。只识别程序实际读到的转换，未观察到的中间编辑不猜测；不使用mtime、保存次数或新Task台账。

原 `agent send --remind` 与事件检查点对同一准确 `mail:<MID>` 共享来源占位，无论哪个先提交，另一个都不再重复提醒。定时检查点有独立身份，不能因为引用过同一原件就取消以后已明确预约的工作。不同正文只因语义相似不会被猜测合并。

共享来源只在程序完成资格检查、真正准备调用原唤醒器时占用。自动检查被暂停、取消或资格不足时，只记本检查点的结果，不占用人工联系入口。原显式提醒有自己的持久请求身份，可处理尚未提交或被自动通道明确拒绝的来源一次；已经submitted/uncertain的来源仍防叠加，重启与交错重入不改变这个事实。

STOP仍由原注入器强制检查。只暂停铸币接续、保留其他联系能力时，可显式配置本安装的Home暂停：

```text
paos mint pause S034 --reason "Human明确暂停自动接续"
paos mint resume S034
```

暂停标记在Data/mint-paused，所有托管与手动check都读取它；resume只移除这份铸币标记，不移除原STOP。单检查点用cancel，单责任用Task waiting。首版不声称App内的停止按钮已自动写入这些暂停事实。未结束的责任与原会话、模型保持。

## 托管和采用

由Rooter按正常固定发行重载原 `content watch`，不另装各Harness服务。程序只读取登记Home的TODO，Rooter也走相同消费者；这些文件继续被内容索引排除。启动读取已登记定义，按带时区墙钟恢复到期点；正常文件事件更新定义，已提交/未知账本阻止重发。忙时沿原Harness受理或拒绝合同，不造通用队列。

`content watch --mint-paused-home HOME` 可附加本次托管的明确暂停；常规持久暂停使用上面的mint pause。采用前先登记仍暂停的同事，不能用新程序恢复他们。

真实验收须由允许工作的原Owner完成：检查点命中→原生受理→本人实读TODO和来源→实际业务接续。仅单测、ready或accepted都不代替这条回证。既有上下文/接收器准备Hook保持，未因本程序存在而删除。
