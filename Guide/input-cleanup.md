# 任务完成后的输入清理

真实责任进入本人 TODO，原信挂在该 Task 的 `source_refs`。成果及独有 Human 原话先回到项目或 EXM 的现有主题，普通交接载体不默认永久归档。很小的随手事项不用强建 Task。

## 在原完成入口一次交清

- 自动新建的 Mail Task：`paos mail result <project> <self> <MID> --result "结果" --artifact-ref <成果>`。
- 已有普通 Task 或按原 Human 决定验收的整体事项：原 `paos task accept <self> --task <TaskID> --artifact <成果> --basis <依据> --remaining <剩余事项>`。原审批和 CAT 合同保持，不重复验收。
- 安装级 Rooter 复用 `mail rooter-result` 的相同清理参数。

两条入口先提交业务完成，再默认评估输入清理，`--cleanup-inputs` 保留为同义显式参数。未传 `--preserved-ref` 时，使用 Task 的 `artifact_ref`；`task accept` 使用本次已核成果。自动成果须为本项目内可读文件，Rooter另可读已登记Project。缺失或不可读时业务照常完成、输入保留，回执说明原因及正式 `input-cleanup` 补办命令，无需重做验收。

调用方正常结项表示已将必要成果与独有Human原话归位。若原话在另一份EXM/System正文、云端权威原件或其他已完成业务入口，显式传 `--preserved-ref <实际定位>`；此参数最高优先，保留原有业务定位合同，由结项者承担归位判断，不套用自动成果的项目范围或猜测正文价值。不能把唯一原话换成摘要，也不能把将被删除的 Mail/Notice 自己当成保留入口。无需为普通旧回执再造意图稿或逐封审批。

`mail result` 挂靠已有大 Task 时只结束本次输入，不会结束整个大 Task；此时返回 `task_unfinished`，不清理其输入。`task accept` 完成的任务可办结它本人已 claim、实读的关联 Notice；其他未读输入不会因关联到它就假装已读。

Rooter 用本人 `task accept rooter-001` 验收时，`--artifact` 和 `--basis` 可引用当前安装已登记 Project 内的原件，跨库请给绝对文件路径。无需复制成果进 Rooter Home；未登记、越出登记根或缺失的原件仍拒绝。普通 Project 的成果范围保持本项目。验收只更新本人 TODO，`--cleanup-inputs` 也仍只清理本人 Home 的输入，活跃依赖保护不变。

## 独立补办与批量处理

按已结束 Task 成组收尾：`paos input-cleanup <self> --task <TaskID> --preserved-ref <保留入口>`。单条输入使用 `--message-id <MID>` 或 `--notice-id <NoticeID>`。未完成 Task 仍引用的输入返回具体依赖者；确已归档的 Mail 留在原历史批次。

未完依赖同时核 `mail:<MID>`、`notice:<NoticeID>` 和本人Home内对应Mail/Notice文件的绝对路径。Windows的正反斜线按同一文件定位；已登记历史收件身份沿准确原Notice保护。依赖Task进入done或cancelled后解除保护，其他文件或其他Home的路径不会被当成本输入。

已由原 Owner/Human 撤回或替代的旧输入可在同一命令指定 `--disposition withdrawn|superseded --decided-by <原决定者> --decision-ref <原决定>`。只按准确决定处理，不伪造 read/handled。旧通信按已确认结束的业务组批量执行，不要求重新研究或建立另一套审批。

早期已有 Mail 而从未生成 Notice 时，明确的撤回/替代仍可成组清理；删除标记记录 `notice_missing=true`，未知的 `was_read/was_handled` 为 null，不补造 Notice 或消费事实。普通 `consumed_deleted` 没有消费证明仍拒绝，未完任务依赖继续保留。

## 删除与重投

每个收件人的 `mailbox/.deleted/<MID>.json` 留最小身份、收尾方式和去重事实，先写标记再删除 Mail、Notice 及侧记录；独立 Notice 使用 `notices/.deleted/`。这些记录不保存正文，也不是历史库。原 dispatch 不改写，同 MID 重投不会重建副本或再次提醒，同 MID 的其他收件人不受影响。

清理后仍可用原 `attention source-status`（Rooter用 `attention rooter-source-status`）查询原来源。已删除时返回 `state=deleted` 和 `deletion` 中的收尾事实、保留入口，不把预期删除误报为Notice丢失，也不伪造一条仍存在的Notice。原未删除输入的读取格式保持。

工位迁址为S号后，同一已登记Home的历史收件身份仍沿原Notice与原read/handled记录核消费。正常读面、独立清理和Task默认清理使用同一登记定位；不改旧邮件/Notice身份来制造消费。删除记录属于当前合法Home，保存准确原Notice定位；其他Home的身份或目录中误放的他人输入不能因此获得清理授权。

迁址前已归档的输入也按同一登记关系识别，返回 `archived_retained`，不改旧归档收件身份或历史文件。同一Task同时引用Mail及其原Notice时作为同一组保留，重入不重新删除或伪造消费。

TODO、文件删除和 CAT 不是同一个事务。任务已完成但个别文件清理失败时，任务不回滚，回执给出 `cleanup_pending`、失败文件和同一 `input-cleanup` 补办入口。不得把部分成功说成全部完成。

## Stop 的本批边界

`Current.inflight` 是在途说明，不作为全局停机信号；Current 的等待只影响对应任务，其他已授权、无等待的 TODO 可继续。只有最终 Stop 才将正在看的 CAT 席位记为 offline；续工不先离线。STOP 和人工中断仍优先。

Codex 多次 Stop block 和同请求内事件粒度仍需真实 Desktop 实测，本批不据单测宣告支持，也不扩展各 Harness 的忙时队列。有限试验的范围与正常配置步骤见[Desktop Stop 试验说明](../Core/tests/manual/CODEX-STOP-PROBE.md)。
