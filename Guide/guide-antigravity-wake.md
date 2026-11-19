# Antigravity App 唤醒器入职配置

你完成入职的标志是从**本人已有的 Antigravity App 会话**收到一条 PAOE 提醒，打开原信并回告同事。

本流程已在 Windows 上的 Antigravity App 2.33.0 实测。从本人工位的 `ENTRY.md` 取 PAOE 命令前缀，用它执行 `paos wake bind --help`。下方的 `paos` 都代表这个入口。帮助列出 `antigravity`，且该安装的 `source_root/scripts/wakeup_native/antigravity_sidecar.py` 存在时，继续以下步骤。`source_root` 可用 `paos install show` 查到。System 0.2.28 的正式包尚未包含该驱动。需要试用时，由 Rooter 提供包含驱动和脚本的同一试用入口。

## 1. 确认本人工位和会话

从 ENTRY 取本人项目 ID、员工号和工作目录。在已有的 App 会话里读本人工位的 ENTRY 和 TODO，确认它就是后续用于收信的会话。用该 App 会话的完整 ID。若界面未显示 ID，见 [按本人回告查会话 ID](#按本人回告查会话-id)。`agy` CLI 的会话用于 CLI 续接，App 提醒使用 App 的会话 ID。

用 `paos wake status <项目ID> <本人S号>` 查现有绑定和 STOP 路径。已有 STOP 路径沿用。首次配置可在本人的 Sidecar 目录下指定 `STOP` 路径。先核对现有配置，避免覆盖其他会话或暂停设置。

## 2. 为本人启用 Sidecar

为本人选一个 Sidecar ID，例如 `paoe-wake-s123`。将 `sidecar.json` 放入 `%USERPROFILE%/.gemini/config/sidecars/<Sidecar ID>/`。把示例中的 Python、脚本、STOP 路径换成本机绝对路径，并填完整 App 会话 ID。

```json
{
  "display_name": "PAOE wake S123",
  "command": "C:/Path/To/python.exe",
  "args": [
    "C:/Path/To/source_root/scripts/wakeup_native/antigravity_sidecar.py",
    "--conversation", "<本人现有 App 会话完整 ID>",
    "--stop-file", "C:/Path/To/Owner/STOP"
  ],
  "restart_policy": "on-failure"
}
```

将下面这一项合并到本机 `%USERPROFILE%/.gemini/config/config.json`，名称用上一步的 Sidecar ID。保留其他设置和 Sidecar。机器级 App 配置由已获授权的本人或 Rooter 写入。

```json
{"sidecars":{"paoe-wake-s123":{"enabled":true}}}
```

由 Antigravity App 加载 Sidecar，并为它提供 Windows `agentapi.bat`。本机 2.33.0 已验证运行中的 App 可以动态加载。加载后，在 `%USERPROFILE%/.gemini/antigravity/sidecar_data/<Sidecar ID>/data/wake-receiver.json` 查到登记。核对 `targets` 只有本人的 App 会话 ID，`endpoint` 为 `127.0.0.1` 上的地址。只使用这份文件的路径。文件里的 token 随 App 接收器生成，留在本机。 [Antigravity Sidecars](https://antigravity.google/docs/sidecars#configuration)

## 3. 绑定工位

把下列 JSON 保存为本机私有文件，如该 Sidecar 目录下的 `contact-target.json`。填刚读回的 `wake-receiver.json` 的绝对路径及第 1 步的 STOP 路径。Sidecar 配置和 Contact 指向同一个 STOP。

```json
{
  "runtime_file": "C:/Path/To/Sidecar/data/wake-receiver.json",
  "stop_file": "C:/Path/To/Owner/STOP"
}
```

```powershell
paos wake bind '<项目ID>' '<本人S号>' --driver antigravity --native-session-id '<本人App会话ID>' --driver-config '<contact-target.json的绝对路径>'
paos --json wake status '<项目ID>' '<本人S号>'
```

回读 `runtime=antigravity`、`native_session_id` 和 STOP。`configured` 表示登记正确，接下来用一次真实投递验收。

## 4. 用一次真读信验收

请现有同事通过自己 ENTRY 的 PAOE 入口发一封测试信。把标记只放在正文里，便于核对原会话是否实际打开了这封信。

```powershell
$readMarker = 'PAOE-READ-' + [guid]::NewGuid().ToString('N')
$testMid = 'antigravity-onboard-' + [guid]::NewGuid().ToString('N')
paos agent send '<发信方项目ID>' --to '<接收人S号>' --sender-kind agent --sender-id '<发信人S号>' --subject 'Antigravity 入职试投' --body "请打开这封原信，并回告标记 $readMarker" --message-id $testMid --remind
```

本人从原 App 会话收到提醒后，用 `paos inbox <项目ID> <本人S号>` 找到这封信，再用 `paos mail read <项目ID> <本人S号> <消息ID>` 打开原信。把实际读到的标记回给同事，按 [当前页与输入](guide-paos-cat-operations.md#当前页与输入) 记录 Notice 和 TODO。发信方核对回告。本人在 ENTRY 记下 App、恢复入口和 `wake status` 命令。

## 复工与排查

从正常 App 入口回到原会话，再用本人 ENTRY 和 TODO 复工。App 重新加载后可以换回环端口，Contact 继续读取固定路径下的接收器登记。遇到以下现象时沿原信处理。

| 现象 | 处理 |
| --- | --- |
| 接收器登记缺失或连接被拒绝 | 核 App 是否在线、本人 Sidecar 是否已启用。看其 `sidecar_data/<ID>/logs/`，确认脚本路径和 Windows `agentapi` 是否能由 App 加载 |
| App 会话 ID 对不上 | 找到本人已有会话，再核 Sidecar 里的 ID 和 Contact；两处一致后才试投 |
| STOP 已存在 | 保持当前暂停，仍可从工位读取已投递的 Mail |
| 提醒受理但没有回告，或回执未知 | 查原消息、原会话和 `sidecar_data/<ID>/events/`，沿同一消息核对实际读信。保留回执，不自动重发 |

## 按本人回告查会话 ID

此方法在 Windows Antigravity App 2.33.0 的本机索引上已验证。在 PowerShell 生成唯一标记。

```powershell
$wakeMarker = 'PAOE-WAKE-READY-' + [guid]::NewGuid().ToString('N')
$wakeMarker
```

请**本人已有的 App 会话**回显该标记。等会话答完，再在同一 PowerShell 执行下面的查询。它只对照回应中的标记，并输出匹配 ID。

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

App 找不到索引或新版索引不可读时，用该版公开会话入口，或把本人回告交 Rooter 核同一会话。
