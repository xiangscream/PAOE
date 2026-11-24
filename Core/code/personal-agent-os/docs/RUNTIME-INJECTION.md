# 原生消息注入

`scripts/runtime_injection.py` 向已配置的原生会话发送一次消息。Python 接口：

```python
from runtime_injection import inject
receipt = inject(target, message)  # scripts 已在 Python 模块路径中
```

独立 CLI 为 `python scripts/runtime_injection.py`，从标准输入读取 UTF-8 JSON，向标准输出返回 JSON；成功退出 0，调用错误退出 1。

```json
{"target":{"runtime":"workbuddy","session_id":"已授权原生会话ID","runtime_file":"C:/path/to/product-authorized-extension/.runtime.json"},"message":"请读取当前工位新消息并继续本人责任。"}
```

目标来自已配置的真实联系信息：

| runtime | 必填目标字段 |
|---|---|
| codex | `session_id`、`extension.receiver_runtime_file`；接收器由目标本人从正常 Desktop 环境准备，发送方不借 Desktop 身份 |
| opencode v1 | `session_id`、`base_url`；原服务应已运行；`api_version`省略或为1 |
| opencode v2 | `session_id`、`base_url`、`api_version:2`、`auth_file`；使用已启动服务的正常Basic授权 |
| workbuddy | `session_id`、`runtime_file`；正常加载的本地扩展须已授权该目标 |
| antigravity | `session_id`、`runtime_file`；Antigravity App 内启用 Sidecar，并授权同一个已有会话 |
| dsh | `session_id`、`receiver_file`、`stop_file`（0.1 插件执行前要求已证 STOP 定位，只登记路径不建暂停文件）、可选 `mode`（`queue`/`steer`）；DSH `wake-receiver` 已加载 |

各目标均可提供显式 `stop_file`。文件存在即停止发送；不从 Project 或 Work 推导停止路径。OpenCode/WorkBuddy/Antigravity/DSH HTTP 可用 `timeout_seconds` 设置原生调用超时，默认 30 秒。Windows locator 在 WSL 按已有路径解析合同处理。

默认省略模型参数，继承目标当前选择。只有 Human 明确指定时才给 `inject(..., model=...)` 或输入 JSON 的 `model`：Codex/WorkBuddy 为原生模型名字符串，OpenCode v1为含 `providerID` 与 `modelID` 的对象。OpenCode v2、Antigravity 与 DSH 的单条prompt不接受模型参数；本工具遇到显式模型参数会拒绝，不额外调用持久化模型切换接口。

`paos wake trigger <project> <home> --model MODEL` 使用同一合同。OpenCode 必须传一个完整 JSON 参数，不能传 `provider/model` 字符串。Bash/WSL 示例（替换 Project、Home 和现存消息路径，仅在 Human 已指定该模型时执行）：

```bash
paos wake trigger <project> <home> --prompt @<message-file> \
  --model '{"providerID":"opencode","modelID":"mimo-v2.6-flash-free"}'
```

Codex/WorkBuddy 的 `--model` 值是各自的原生模型名字符串，不使用上述 OpenCode 对象。其他 Shell 也须将整个 JSON 保留为一个参数；上例的引用方式适用于 Bash/WSL。

受理结果含 `accepted:true`、`runtime` 和 `session_id`。Codex正常接收器还返回 `native_status_before_submit`，只表示提交前观察；OpenCode v1含原生 `http_status:204`，v2为200并返回已关联的`message_id`和原生`native_disposition`（steer或queue）；WorkBuddy含本次原生 `request_id` 与 `native_disposition`，不返回整段SDK内容；DSH含本次 `request_id`、`native_disposition` 与 `http_status:200`。明确拒绝为 `InjectionError` / `accepted:false`；可能已发送但回执不明为 `InjectionUncertain` / `accepted:null`、`retry:false`。受理不代表业务消费或成果。

Codex正常接收器对明确active/idle/notLoaded向既有App Tools跟进入口提交一次，不因active预先拒绝，也不指定或保证steer/queue；模型与Follow-up设置沿Human。未知状态、STOP和实例核验保持。目标本人更新接收器及确认实际加载，读[本人接收器说明](CODEX-SELF-REMINDER.md)。OpenCode v1按原目录读会话与状态后提交一次prompt_async，204仅表示原生受理，不推定queue或完成；v2的发送与关联回执见下方接入说明。两者仍使用进程退出自动释放的互斥。WorkBuddy使用产品自身调用合同。

WorkBuddy回环建立连接前明确被拒绝时，返回 `receiver_offline` / `receiver_connection_refused` / `accepted:false`。当前扩展在调用sendPrompt前返回的400/401/404为明确拒绝；SDK调用后502、连接超时/复位、响应丢失或关联回执不符仍是结果未知，不据此自动重发。S014等目标仍须取得产品支持的正常扩展安装与权限入口，错误分类不代替恢复。

DSH 只从 receiver 发现文件读取 `url` 与 `secretFile`，secret 内容不写入 Contact、命令行、结果或 Git。目标必须是 `127.0.0.1` 回环；400/401/403/404/409/413/422 与 503 是明确拒绝（503 为 Session controller 未挂载），其余 5xx（含 500）和连接超时/复位、回执丢失或身份不符均保持 unknown，不自动重发。409 `session/agent-busy` 表示另一写入者占用目标，不重试；接收器不创建 Session、不取消回合，STOP 只阻止后续发送，不能声称已停止运行中的回合。

工具不自动重试、启动Runtime、保存attempt或观察模型完成，也不加载Project Store、Work或Notice。旧消息是否已处理由调用方在工位当前读面判断；既有拒绝和不确定回执保持原样，不因实现更新重放。

## Antigravity App 固定会话接入

Antigravity 启动已启用的 Sidecar，为它提供 `agentapi` 和独立数据目录。配置步骤见 System 工位母版的《入职与唤醒器》。Sidecar 使用已获准的 App 会话完整 ID，与 PAOE Contact 共用 STOP 文件。[Google Sidecar 文档](https://antigravity.google/docs/sidecars#agentapi)

安装负责人将 Contact 的 `runtime_file` 指向本机 Sidecar 数据目录里的 `wake-receiver.json`。登记只保存定位，Sidecar 启动时生成回环 endpoint 和本次 token。正常发送沿用 `paos agent send --remind`。接收器用官方 `agentapi send-message` 提交一次，回执核对会话 ID 和单次请求 ID。退出码非零或提交超时回为结果未知。读信和完成由目标会话另行回告。

此入口针对 App 会话。独立 `agy --conversation` 接续 CLI 会话，两种会话的互通需用实际同 ID 证明。

## DSH 固定 Session 接入

DSH 的 `wake-receiver` 插件在 DSH 进程内监听本机回环，并把一条消息准入到已有 Session。PAOE 只登记接收器发现文件、固定 Session 与 STOP 路径定位，不保存 secret。当前 0.1 DSH 插件（`paos-core.mjs`）在模型执行前要求 Contact 具备非空 `stop_file`（否则报 `PAOE Contact has no verified STOP location`），且 `wake bind` 不会为首次 DSH 绑定自动填充 `stop_file`，因此私有配置 JSON 须显式提供 `stop_file`（按 `paos install show` 的 `data_root` 定位到 `<data_root>/runtime/dsh-context/<本人Sxxx>/STOP`；仅登记路径定位，**不要创建该 `STOP` 暂停标记文件**）：

```json
{
  "runtime": "dsh",
  "session_id": "session-<正常接口返回的完整ID>",
  "receiver_file": "<本机DSH_HOME>/wake-receiver/receiver.json",
  "mode": "queue",
  "stop_file": "<当前安装data_root>/runtime/dsh-context/<本人Sxxx>/STOP"
}
```

`receiver_file` 与 `stop_file` 均须为本机绝对路径，`receiver_file` 指向 DSH 正常写出的 `dsh-wake-receiver/v1` 记录；其中 `url` 只能为 `127.0.0.1` 回环，`secretFile` 由驱动在发送时读取。`session_id` 使用正常接口实际返回的完整 ID（形如 `session-<uuid>`）；不要剥掉前缀，也不要把裸 UUID 自动猜补成另一个 ID。Session 的 cwd 由 Human 的实际工作区决定，可以不是 Project 根；Project 工作材料按 ENTRY/Registry 定位，不因 cwd 不同而搬工作区。绑定与补齐沿原本人会话与现有模型办理，保留原账号与已有绑定，普通安装不重置其他员工。绑定错误 Session ID 会得到 `session/not-found`，本工具不自动创建或换 Session。`mode` 省略时为 `queue`，`steer` 只在目标会话正在运行时由 DSH 自身处理。

一次提醒生成一个本次 `requestId`，随请求提交并在受理回执中核对。传输超时或回执丢失时保留该 ID 并返回 unknown；不自动重发，也不生成第二个 UUID 冒充同一次幂等提交。`paos wake status` 的 DSH `receiver` 视图只读发现文件、PID 与 heartbeat，不连接接收器。`prepared=true` 只表示记录、secret 存在，PID 未被确认死亡，且 heartbeat 存在并新鲜；heartbeat 缺失、不可解析或过期均使 `prepared=false`，且任何 `prepared=true` 都不等于在线或已消费。记录可用时清空默认的未注册 `reason`/`next_action`，只在真正缺记录、缺 secret、heartbeat 异常或 PID 已死时给出对应修复提示；不会把健康读面误报成需要重新 bind。在线事实仍由 DSH 侧 `dsh_wake.py status` 或真实受理验证。

## OpenCode v2 Windows接入

正常运行维护者用产品`OPENCODE_PASSWORD`设置本机服务密码，并在本机私有文件保存`{"password":"服务设置的同一密码"}`。`auth_file`只登记该文件路径；密码不写Contact、命令参数、项目成果或Git，不提取其他会话凭据。此合同在Windows OpenCode2.0.32上验证，用户名为产品固定值`opencode`。

```json
{
  "runtime": "opencode", "api_version": 2,
  "session_id": "原生会话ID", "base_url": "http://127.0.0.1:当前端口",
  "auth_file": "C:/本机私有目录/opencode-server-auth.json",
  "stop_file": "C:/原目标的STOP路径",
  "extension": {
    "execution_environment": "windows",
    "windows_python": "C:/实际Python/python.exe"
  }
}
```

按已安装CLI的`wake bind --driver-config`正常登记以上目标，不改原会话ID、模型或STOP。Windows进程直接发送；WSL发送者在任何HTTP请求前选择已登记的Windows Python，沿同一安装Source入口传一次UTF-8 stdin，仅传目标定位字段，不把密码带到子进程参数中。失败后不改走WSL回环或另一版API。

v2路径为：`GET /api/session/<id>`核原ID及`location.directory` → `GET /api/session/active`读全服务活动状态 → STOP → 一次`POST /api/session/<id>/prompt`，正文只有本次`id`和`text`。200回执必须关联相同会话及本次消息ID；丢失、不可解析、错关联或服务端执行结果不明均保持unknown，不重发。与v1的差异由`api_version`显式选择，不做失败后自动探测或降级。

人工查看v2用`opencode --server <URL> --session <ID>`，其客户端也须取得运行维护者设置的正常`OPENCODE_PASSWORD`；Contact不显示密码。v1继续使用`opencode attach`，直至原目标正式迁完。数据迁移、独审、发布和真实业务读取通过前，不切自动Contact。

PAOS 通信层先持久投递原消息，再解析员工联系信息调用同一 `inject`；注入失败不得删除原信。安装升级由正常发布流程统一接线并退役旧消费者，独立模块存在不等于实际安装已采用。
