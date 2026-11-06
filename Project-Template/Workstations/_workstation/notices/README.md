# 入职与唤醒器

## 入职

完成 TODO 的 `ONBOARD`：

1. **了解体系**：读 [AGENTS](../../../AGENTS.md) 和 [ENTRY](../ENTRY.md)。System 管运行，Libraries 管方法，项目库管业务。
2. **继承业务**：沿 [INDEX](../../../INDEX.md) 读原件与交接，确认目标、现状、未完事项；下一步写本人 TODO。
3. **更新成员信息**：补 [TEAM](../../../TEAM.md) 本人职责、专长和工位入口；职责变化与 Coordinator 对齐。
4. **配置唤醒器**：按本人 Harness 执行下方命令，完成真实 Mail 验收，把使用和恢复命令写回 ENTRY。

## 代码

| 文件 | 用途 |
| --- | --- |
| [codex.py](codex.py) | Codex：绑定、准备接收器、查状态、单次提醒 |
| [opencode.py](opencode.py) | OpenCode / OpenCode2：绑定原生服务、查状态、单次提醒 |
| [wake_entry.py](wake_entry.py) | 共用安装定位与本人工位校验，调用 Core |

底层实现位于 `paos install show` 返回的 `source_root`：Codex 为 `scripts/wakeup_native/codex_receiver.py`，准备入口为 `scripts/codex_receiver_session_start.py`；OpenCode 为 `scripts/runtime_injection.py` 的 `_opencode` / `_opencode_v2`。代码共用这些原件。

## 配置与启动

从本人工位目录执行。`PAOS_INSTALLATION_FILE` 指向 ENTRY 中的安装描述；也可在 `bind` / `status` 等子命令前加 `--installation-file "绝对路径"`。脚本从 Registry 确认本人身份，母版目录不可直接绑定。

**Codex：**

```text
python notices/codex.py bind --session-id <本人真实ThreadID>
python notices/codex.py prepare
python notices/codex.py status
```

`prepare` 必须由本人在 Codex Desktop 工具环境执行。自动恢复复用已安装 SessionStart Hook；新建或修改的 Hook 需在官方入口审阅信任，见 [Hooks](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks)。人工准备与自动恢复分别验证。

**OpenCode / OpenCode2：**

OpenCode2 的私有目标配置 JSON 填：

```json
{"base_url":"http://127.0.0.1:实际服务端口","api_version":2,"auth_file":"本机授权文件绝对路径"}
```

```text
python notices/opencode.py bind --session-id <本人真实SessionID> --driver-config <本机私有配置JSON>
python notices/opencode.py status
```

`auth_file` 指向现有服务授权文件；沿用本机已登记的服务与模型。旧版 OpenCode 使用对应驱动配置，不套用 `api_version: 2`。

## 使用与验收

单次原生提醒：`python notices/codex.py wake --prompt "读取本人TODO并继续"`；OpenCode 换成 `opencode.py`。这条命令只提醒，不保存 Mail；正式交接仍用 ENTRY 中的 `paos agent send --remind`。

入职验收：同事发一条 Mail → 本人收到提醒 → 实读原信 → 更新 TODO、处理 Notice → 回告 → 恢复原会话并接续。配置存在、提醒受理、实际消费分别记录；四项入职要求完成后勾选 `ONBOARD`。

保留原 Session、模型和 STOP；状态未知或提醒结果不明时查原信，不自动重发。`notice-*.md` 是消息记录；本页和脚本不算待处理 Notice。
