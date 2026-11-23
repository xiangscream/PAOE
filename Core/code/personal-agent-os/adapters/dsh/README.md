# DSH 中的 PAOE 工位

此插件在选定 DSH 原会话的业务请求中带入工位和任务原文。它调用该安装的 `paos context read`、`context stop` 和 Contact 读面。登记之外的会话沿用 DSH 自身行为。适配的宿主接口版本为 0.2.2-rc.2。

## 安装与选定会话

先在自己的 DSH 原会话运行 `paos --json wake status <项目号> <员工号>`。核对 `configured` 为 true、`runtime` 为 `dsh`，并将 `native_session_id` 与宿主显示的当前会话 ID 核对。二者一致后，将该 ID 用作下方 `sessions` 的键。

安装负责人从选定的安装描述读取 `source_root`，在其中运行 `python -X utf8 -B scripts/paos.py --installation-file <安装描述> --json context read <员工号> --reason resume`。查看 `task_id`、`documents` 中的工位与原件路径，以及 `missing`。空 `task_id` 表示本次读取没有选定任务。若该 Core 的帮助中没有 `context`，先由安装负责人配好含此命令的正式版本或限定试用入口，再启用插件。

由本机安装负责人从 DSH 插件管理器选择本目录安装 Host bundle。配置项 `paoe-session-context` 随包登记，空配置不选择任何会话。给该项提供安装描述及本次启用的工位，填写实际值。

```yaml
installation: <本机已登记的 installation.json 绝对路径>
sessions:
  <原 DSH Session ID>:
    project: '<Project ID>'
    home: '<员工号>'
```

Windows 默认从 PATH 调用 `python`，也可在同一配置中填写 `python` 的绝对路径。已有专用房角色的工位需要 `catUrl`，试用用指定的隔离 CAT。会话选择以本机 Contact 为准，两个 ID 必须对应。插件从当前 DSH 安装或实际启动入口解析 AgentLoop，再加载该循环使用的同一份消息 SDK。

## 运行与检查

首次业务请求、恢复和压缩后，读取当前工位所需原件。每个正常 AgentLoop 请求在 `llm/stream` 对照实际消息和输入来源。同阶段相同的原文复用已入会话的副本；角色受专用房管理时，在下一次动作前向 Core 复核。缺失必读原件会报告路径，仍可在本机补读。容量依据宿主当前窗口和当前请求的计量，未知窗口记为未知。

历史挤占窗口时，原请求先退出；回到空闲状态后用宿主的正式压缩入口，核对同一 Task 后至多接续一次。选定原件本身过大时交给负责人调整范围。Human 中断或工位 STOP 取消待执行的自动接续。普通停止按同一原生回合至多纠偏一次。

本机证据在 `Data/runtime/dsh-context/<员工号>/events.jsonl`，只记录工位、回合、检查位置、原件版本和计量。实际业务消费仍以原会话回复、工位处理记录和成果为准。移除本会话的配置即可撤回试用，经 DSH 正常重载后回读生效状态。
