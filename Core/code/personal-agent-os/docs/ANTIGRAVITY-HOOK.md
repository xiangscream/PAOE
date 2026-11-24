# Antigravity App 上下文 Hook

用原生 `PreInvocation` 为已登记的会话读取 PAOE 必读原文。首次请求、原会话恢复和压缩后的下一次请求都走这个入口。每次读取使用相同的 `context read --reason request` 合同，由 Core 决定当前原件。没有单独的 Antigravity 恢复事件标记。

## 审阅与配置

App 的项目选择器决定会话工作区；聊天中的 `@` 引用只提供材料。配置前确认项目真实文件夹可用，并对照目标会话的 `workspace_uris` 与 Hook 事件确认作用域。重新绑定文件夹后，既有会话仍可能保留创建时的工作区记录；正式采用按目标原会话的实际结果登记。

由安装负责人在已审阅的工作区 `.agents/hooks.json`，或已采用插件的 `hooks.json` 中添加这项配置。应用现有设置的信任流程。以下为一个已登记 Project 工位的模板。将三个路径替换为本机绝对路径，将项目号和员工号替换为同一工位的登记值。多个工位使用各自的 Hook 名称和相应登记。

```json
{
  "paoe-SXXX-context": {
    "PreInvocation": [
      {
        "type": "command",
        "command": "\"<Python 可执行文件>\" \"<当前 Core scripts/paos_antigravity_hook.py>\" --installation-file \"<installation.json>\" --project <项目号> --agent <S号> --event PreInvocation --cat-url \"<已登记的 CAT 地址>\"",
        "timeout": 15
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "\"<Python 可执行文件>\" \"<当前 Core scripts/paos_antigravity_hook.py>\" --installation-file \"<installation.json>\" --project <项目号> --agent <S号> --event Stop --cat-url \"<已登记的 CAT 地址>\"",
        "timeout": 5
      }
    ]
  }
}
```

Hook 从同一安装描述取得 Contact 和工位原件，用 Contact 的会话 ID 匹配宿主提供的 `conversationId`，不借用全局默认安装。正常输出是包含完整正文的 `ephemeralMessage`。共用读取失败、缺必读原件或内部读取超时会返回原生 `terminationBehavior=terminate` 和界面错误提示。共用读取的 8 秒时限留出宿主回传时间。

Stop 沿 `context stop` 更新本人 CAT 状态，宿主的后台活动仍由宿主报告。已登记团队角色的工位，读取与停止都使用同一 `--cat-url`；未使用 CAT 的工位可在两处省略该参数。CLI 实测同一回合由 Stop 请求重入时 `executionNum` 也递增，当前采用共用动作的 `--reentry` 禁续跑分支，等待可辨认同一回合的宿主标识。阶段交付仍走显式动作，原提醒继续由已登记 Sidecar 单次提交。

## 验收

- 在同一已登记的原会话分别验首次或恢复后的请求，以及原件更新后的下一次请求。模型须实际回传仅出现在指定原文里的标记。
- 在合成工作区故意移走必读原件。记录界面错误和模型是否收到请求。再分别记录宿主遇到命令不可启动、无效输出和超时的真实行为。
- 在同一宿主进程内修改独立工作区的 Hook 配置。通过下一次请求的标记确认是否热更新。切换或启用配置时以实际宿主证据为准。
- 实际停止时核对终止原因与是否还有后台活动，确认人工中断后没有新回合。仅收到 Stop 不代表阶段已交付。

Antigravity CLI 1.5.12 的隔离试验中，不存在的命令、非零退出、非法 JSON 和宿主超时均允许模型继续。App 2.34.0 已另行实测：合法 `terminate` 在模型前停止；同一原会话及宿主进程中，修改后的 Hook 可注入隐藏标记。App 遇到命令缺失、脚本非零退出、非法 JSON 时仍调用模型；1 秒限时、计划等待 6 秒的试件约在 1.88 秒报告通用退出 1，模型也继续，宿主未给出专门的超时分类。

PAOE 的主动终止只适用于成功执行到 Hook 并返回合法结果的检查点，不能将宿主加载或执行失败当作模型已被阻断。隔离试件的 Stop 已观测；各业务原会话的 Stop 仍需以对应回合记录确认。

[Antigravity Hook 配置和契约](https://antigravity.google/docs/hooks)
