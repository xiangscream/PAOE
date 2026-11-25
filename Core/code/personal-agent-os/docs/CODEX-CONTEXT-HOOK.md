# Codex：原生事件接共用动作

`scripts/paos_codex_hook.py` 接收宿主标准输入，沿事件 session_id 查原 Contact；如工具环境提供 CODEX_THREAD_ID，二者必须相符。未登记会话不参加 PAOE，歧义、原件缺失和未知错误返回显式停止。原 STOP 始终优先，不改身份、模型或凭据。

| 宿主事件 | 共用动作与返回 |
|---|---|
| SessionStart startup/resume | 本人接收准备 + `context read HOME --reason startup/resume`；完整原文进 additionalContext |
| SessionStart compact | 同一原会话准备 + `context read HOME --reason compact`，供压缩后的下一轮读取 |
| UserPromptSubmit | 本人准备 + `context read HOME --reason request`，不记录或转发 prompt |
| Stop | `context stop HOME --event codex:SESSION:TURN`；stop_hook_active=true 追加 --reentry |

Stop 的 action=continue 翻译为原生 `decision=block` 和 next_action；action=stop 正常结束。原生回合 ID 不变时共用动作最多允许一次，宿主明确重入也不继续。Stop 只更新本人参与状态与判断后续行动，不调用 stage deliver，不验收 Task。当前 Waiting/Inflight 由共用动作读取。

Windows Hook 缺少本人 Desktop 环境时继续返回已登记会话的业务原文，同时请当前原会话从自己的终端执行一次 `orient <项目> <工位> --resume`（Rooter 用 `attention rooter-show --resume`）。命令核对恢复工位与真实工具环境的本人身份，再沿原登记、STOP 与复用检查执行。线程不符时直接停止。只有原生事件实际进入、输出实际进入模型及原信实际处理，才能分别确认对应结果。

## 配置与采用

限定原会话的渐进采用用[只追加的会话选择配置](CODEX-SELECTED-HOOK.md)：保留旧准备定义及位置。已获信任的选中入口对 startup、resume、compact 与提交事件执行本人准备和上下文读取。此模式避免新增定义审阅前中断其他会话；以下整体替换方式仅用于整体切换，不用于限定试用。

Rooter 通过受支持宿主入口，把下面同一命令配置到 SessionStart（matcher `^(startup|resume|compact)$`）、UserPromptSubmit 和 Stop：

```text
<Python> -X utf8 -B <已安装scripts>/paos_codex_hook.py --installation-file <安装描述> --cat-url <本机CAT地址>
```

command handler 使用同步模式，timeout 30 秒。读原文的两个事件设置 `additionalContextLimit: 0` 才能要求宿主把全部原文直接传入模型；启用前检查共用读取返回的正文范围及长度。默认限制会截取或落盘，不能将其说成已完整装载。Stop 不设置这个字段。事件定义与命令变化要由原生 `/hooks` 或相应支持入口审阅；不要直接写 trusted_hash。

采用后替换原有指向 codex_receiver_session_start.py 的两个配置，避免同事件重复准备/注入；原脚本继续保留显式准备和旧调用接口。测试环境必须给独立安装描述及隔离 CAT，不能借生产 Home 测 Stop。

完整 JSON 回执被校验为同一 Home/事件。缺原件、非零退出、格式错误、超时均返回 continue=false；这保证适配器正常返回时的停止语义。命令不存在或宿主在进程外中止等异常，要另外测宿主行为，不能用 Python 单测证明。

## 证据边界

[官方 Hooks](https://learn.chatgpt.com/docs/hooks)区分本地与云编排。当前候选不改变编排方式，不承诺不支持本地 command 的宿主能调用它。真实原会话采用与自然输入/压缩/Stop 证据由 Rooter 安排，隔离 subprocess 结果不是自然 Hook 或模型消费证据。

复验：`python -m unittest discover -s ../../tests -p test_codex_context_hook.py -v`；与共用 CLI 的真实隔离读写配对，覆盖完整原文、缺项、STOP、错会话、重入、事件去重、本人 CAT 离线和错误回执。其后运行 `python scripts/verify.py`。
