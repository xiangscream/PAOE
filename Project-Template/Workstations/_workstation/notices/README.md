# 入职与唤醒器

## 入职

完成 TODO 的 `ONBOARD`：

1. **了解体系**：读 [AGENTS](../../../AGENTS.md) 和 [ENTRY](../ENTRY.md)。System 管运行，Libraries 管方法，项目库管业务。
2. **继承业务**：沿 [INDEX](../../../INDEX.md) 读原件与交接，确认目标、现状、未完事项；下一步写本人 TODO。
3. **更新成员信息**：补 [TEAM](../../../TEAM.md) 本人职责、专长和工位入口；职责变化与 Coordinator 对齐。
4. **建立联系入口并配置唤醒器**：从ENTRY打开OPS的“生成本人公开联系包”，调用已登记安装中的公开包装；再按本人Harness执行下方命令，沿已有真实Mail完成验收，把使用和恢复入口写回ENTRY。

## 代码

| 文件 | 用途 |
| --- | --- |
| [codex.py](codex.py) | Codex：绑定、准备接收器、查状态、单次提醒 |
| [opencode.py](opencode.py) | OpenCode / OpenCode2：绑定原生服务、查状态、单次提醒 |
| [dsh.py](dsh.py) | DSH：绑定固定 Session、查状态、单次提醒 |
| [wake_entry.py](wake_entry.py) | 共用安装定位与本人工位校验，调用 Core |

本页脚本调用当前安装的Core。公开联系包命令只在OPS所链接的“工位Contact薄入口”维护；日常入职按该公开入口执行，无需调用实现函数。

## 配置与启动

从本人工位目录执行。`PAOS_INSTALLATION_FILE` 指向 ENTRY 中的安装描述；也可在 `bind` / `status` 等子命令前加 `--installation-file "绝对路径"`。脚本从 Registry 确认本人身份，母版目录不可直接绑定。

### Codex

```text
python notices/codex.py bind --session-id <本人真实ThreadID>
python notices/codex.py prepare
python notices/codex.py status
```

已登记 Codex 接收器的本人从原 Desktop 用 `paos orient <project> <本人Sxxx> --resume` 复工，入口同时准备接收器。宿主可用时，SessionStart 和 UserPromptSubmit 也调用准备逻辑。新建或修改的 Hook 在官方入口审阅，实际执行看接收器日志。 [Hooks](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks)

### OpenCode / OpenCode2

OpenCode2 的私有目标配置 JSON 填：

```json
{"base_url":"http://127.0.0.1:实际服务端口","api_version":2,"auth_file":"本机授权文件绝对路径"}
```

```text
python notices/opencode.py bind --session-id <本人真实SessionID> --driver-config <本机私有配置JSON>
python notices/opencode.py status
```

`auth_file` 指向现有服务授权文件；沿用本机已登记的服务与模型。旧版 OpenCode 使用对应驱动配置，不套用 `api_version: 2`。

### DSH

DSH 的固定 Session 使用正常接口返回的完整 ID（形如 `session-<uuid>`），不要剥前缀或用裸 UUID 猜补。Session 的 cwd 可以是 Human 的实际工作区，不必等于项目根；Project 工作材料按 ENTRY 定位，不强迫搬工作区。私有目标配置只登记接收器发现文件，不复制 secret。`receiver_file` 填本机绝对路径：

```json
{"receiver_file":"<本机DSH_HOME>/wake-receiver/receiver.json","mode":"queue"}
```

```text
python notices/dsh.py bind --session-id <本人DSH_SESSION_ID> --driver-config <本机私有配置JSON>
python notices/dsh.py status
```

接收器由 DSH 的 `wake-receiver` 插件提供，只监听 `127.0.0.1`。`status` 读取绑定和接收器发现文件的 PID/heartbeat 事实，不连接入口；`prepared=true` 只表示记录、secret 存在、PID 未被确认死亡且 heartbeat 新鲜，heartbeat 缺失/不可解析/过期均为未准备，且不等于在线。记录可用时不再显示未注册 `reason` 或重新 bind 的 `next_action`，只有真正异常才给修复提示。需要在线健康时用 DSH 侧 `dsh_wake.py status`。接收器不创建 Session、不取消回合；PAOE STOP 只阻止后续注入，不能声称已停止运行中的回合。

### Antigravity App

本流程已在 Windows 上的 Antigravity App 2.33.0（Sidecar 唤醒）与 2.34.0（工作区 Hook 接入）实测。System 0.2.29 起支持该驱动。从本人 [ENTRY](../ENTRY.md) 取 PAOE 命令前缀。用 `paos wake bind --help` 核对 `antigravity`，用 `paos install show` 核对该安装的 `source_root`。下文的 `antigravity_sidecar.py` 位于此 Source 的 `scripts/wakeup_native/`。

#### 确认本人 App 会话

在以后用于收信的原 App 会话里读本人 ENTRY 和 TODO，记下项目 ID、员工号和 App 会话完整 ID。界面未显示 ID 时，见 [按本人回告查会话 ID](#按本人回告查会话-id)。`agy` CLI 用自己的会话 ID 续接。用 `paos wake status <项目ID> <本人S号>` 核对现有绑定与 STOP 路径，沿用已有 STOP。

#### 启用本人的 Sidecar

为本人选一个 Sidecar ID，例如 `paoe-wake-s123`。将以下配置保存为 `%USERPROFILE%/.gemini/config/sidecars/<Sidecar ID>/sidecar.json`。填本机 Python、Source 脚本、STOP 的绝对路径，以及原 App 会话 ID。首次配置可把 STOP 路径设在本人的 Sidecar 目录。

```json
{
  "display_name": "PAOE wake S123",
  "command": "<本机 python.exe 的绝对路径>",
  "args": [
    "<当前 Source 中 antigravity_sidecar.py 的绝对路径>",
    "--conversation", "<本人现有 App 会话完整 ID>",
    "--stop-file", "<本人 STOP 的绝对路径>"
  ],
  "restart_policy": "on-failure"
}
```

在 `%USERPROFILE%/.gemini/config/config.json` 合并下面这一项，名称用本人的 Sidecar ID。保留其他设置和 Sidecar。机器级配置由已获授权的本人或 Rooter 写入。 [Antigravity Sidecars](https://antigravity.google/docs/sidecars#configuration)

```json
{"sidecars":{"paoe-wake-s123":{"enabled":true}}}
```

Antigravity App 负责加载 Sidecar 并提供 Windows `agentapi.bat`。本机 2.33.0 已验证可动态加载。加载后，到 `%USERPROFILE%/.gemini/antigravity/sidecar_data/<Sidecar ID>/data/wake-receiver.json` 核对 `targets` 只有本人 App 会话 ID，`endpoint` 是 `127.0.0.1` 上的地址。Contact 只登记这份文件的路径，token 留在本机。

#### 绑定工位

把下列 JSON 保存为本机私有的 `contact-target.json`，填写刚读回的登记文件路径。Sidecar 和 Contact 使用同一个 STOP。

```json
{
  "runtime_file": "<本人的 wake-receiver.json 的绝对路径>",
  "stop_file": "<本人 STOP 的绝对路径>"
}
```

```powershell
paos wake bind '<项目ID>' '<本人S号>' --driver antigravity --native-session-id '<本人App会话ID>' --driver-config '<contact-target.json的绝对路径>'
paos --json wake status '<项目ID>' '<本人S号>'
```

回读 `runtime=antigravity`、`native_session_id` 和 STOP，再按本页 [使用与验收](#使用与验收) 发一封测试信，核对原 App 会话实读回告。复工时回到同一个 App 会话。App 重新加载时端口可以变化，Contact 继续读取固定路径下的登记。登记缺失或拒连时查本人 Sidecar 的启用状态和 `sidecar_data/<ID>/logs/`。提醒已受理但没有回告时，沿原信和 `sidecar_data/<ID>/events/` 核对。

#### 工作区 Hook 接入与核验

在 Antigravity App 中接入 PAOE 工作区 Hook（自动注入必读原文与回合 Stop），以已实测路径为准：

1. **选择真实项目目录（`@` 引用不是选项目）**：在桌面 App 的项目选择器明确选中真实项目目录（本地模式选 Local），使会话实际归属该项目。在已有会话里用 `@` 引用其他目录不会切换会话归属，也不会触发该目录的 Hook。
2. **合并写入工作区 `.agents/hooks.json`**：工作区 Hook 保存在项目根目录 `.agents/hooks.json`。同项目多名成员的具名 Hook 合并写入同一文件并保留已有定义，各自沿同一安装描述核对自己的 Contact；部署只接 Hook，不改原会话、模型、STOP 或正式 Store。
3. **无独立 Hooks 菜单**：本版 App（2.34.0）项目设置的「自定义项」可查看技能、规则、插件及自定义 Agent，没有已证实的独立 Hooks 列表或开关菜单。核对或修改 Hook 直接看项目根目录 `.agents/hooks.json`，目录归属看项目设置的「文件夹」。
4. **重绑目录后须开新会话验证**：通过项目设置「文件夹」重新选定项目目录后，已创建的旧会话仍沿用创建时的工作区记录；验证工作区 Hook 生效必须新建会话并核对新会话的项目归属。
5. **分层核验**：把**配置就绪**（`.agents/hooks.json`、Contact 与脚本回读）、**原文实读与原生事件**（原会话转写与 Hook 日志中的注入/Stop）、**实际业务结果**（接手、产文与提交）分开记录，互不替代。隔离试件与原会话业务验证独立取证；当前 24D 同进程注入试件仍为独立待验项。

#### 后台提醒后的收信与公开回复习惯

Antigravity App 的后台唤醒消息以系统提醒进入会话，Human 在聊天界面里不易直接看到原信内容。收到后台提醒后，应先实读工位原信（`paos mail read` 或读取对应 CAT 消息），再在原聊天公开回复中让 Human 一眼看懂协作脉络：

- **短消息直接带原话，长信留核心原话与原件入口**：短消息在公开回复中直接显示发件人、主题和来信原话；长信保留核心请求原话与可点击的原件路径，不省略来信只报结果，同时隐去 token、凭据等敏感字段；
- **结尾标明协作双方**：在回复末尾写清协作双方与原信/房间标识，方便追溯；
- **三段状态分开判断**：原生提醒受理、本人实际读信与发件方收到回告三者各自独立核对，不把 Sidecar 受理当作已读，也不把本端公开回复当作对方已收到交接。

#### 按本人回告查会话 ID

在 PowerShell 生成唯一标记。此方法已在 Windows Antigravity App 2.33.0 的本机索引上验证。

```powershell
$wakeMarker = 'PAOE-WAKE-READY-' + [guid]::NewGuid().ToString('N')
$wakeMarker
```

请本人已有的 App 会话回显该标记。答完后在同一 PowerShell 查 ID。查询只读本机索引，只输出唯一命中的 ID。

```powershell
@'
import sqlite3
import sys
from pathlib import Path

index = Path.home() / ".gemini/antigravity/conversation_summaries.db"
if not index.is_file():
    raise SystemExit("未找到本机 App 索引，请从 App 会话入口或由 Rooter 核对。")
with sqlite3.connect(index.as_uri() + "?mode=ro", uri=True) as db:
    matches = db.execute(
        "SELECT DISTINCT conversation_id FROM conversations_fts "
        "WHERE instr(coalesce(agent_body,''),?) > 0",
        (sys.argv[1],),
    ).fetchall()
if len(matches) != 1:
    raise SystemExit("标记未唯一命中，请确认本人 App 会话已完整回告。")
print(matches[0][0])
'@ | python -X utf8 -B - $wakeMarker
```

新版索引不可读时，从 App 会话入口或请 Rooter 根据本人回告核 ID。

## 使用与验收

单次原生提醒：`python notices/codex.py wake --prompt "读取本人TODO并继续"`；OpenCode 换成 `opencode.py`，DSH 换成 `dsh.py`。这条命令只提醒，不保存 Mail；正式交接仍用 ENTRY 中的 `paos agent send --remind`。

入职验收：同事发一条 Mail → 本人收到提醒 → 实读原信 → 更新 TODO、处理 Notice → 回告 → 恢复原会话并接续。配置存在、提醒受理、实际消费分别记录；四项入职要求完成后勾选 `ONBOARD`。

需要验收实读时，发信方可用一次试投，标记只放在正文。收件人用 `paos inbox <项目ID> <本人S号>` 找到这封信，用 `paos mail read <项目ID> <本人S号> <消息ID>` 打开原信，再回告标记。

```powershell
$readMarker = 'PAOE-READ-' + [guid]::NewGuid().ToString('N')
$testMid = 'wake-onboard-' + [guid]::NewGuid().ToString('N')
paos agent send '<发信方项目ID>' --to '<接收人S号>' --sender-kind agent --sender-id '<发信人S号>' --subject '唤醒入职试投' --body "请打开这封原信，并回告标记 $readMarker" --message-id $testMid --remind
```

保留原 Session、模型和 STOP；状态未知或提醒结果不明时查原信，不自动重发。`notice-*.md` 是消息记录；本页和脚本不算待处理 Notice。
