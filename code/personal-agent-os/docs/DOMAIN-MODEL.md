# PAOE 当前领域模型

> 本文描述 PAOS-portable / PAOE 当前实现，不沿用早期 Project Store、Work、Cycle 或 Session 管理模型。

| 对象 | 含义 | 权威位置 |
|---|---|---|
| Installation | 当前机器的源码、数据、库与可选 Rooter 定位 | installation.json |
| Project Registry | Project Vault 根目录、Home 名册与 Coordinator 定位 | data_root/project-registry/projects/<id>.json |
| Project Vault | 项目业务事实、口径、材料、决策与成果 | Obsidian 项目目录 |
| Project Home | 一个长期 Agent 的身份与责任 | Workstations/<home-id>/ |
| Rooter Home | 安装级维护 Agent，不属于 Project | installation descriptor 的 rooter_home |
| TODO | Home 当前责任 | Home/TODO.md，paos-todo/v4 |
| Mail | 发给 Home 的持久消息原件 | Home/mailbox/<message-id>.md |
| Notice | 输入到达与处理事实 | Home/notices/ |
| Workflow / Skill / Tool | 可复用工作方法与工具说明 | 已登记的共享 Library |
| Runtime Contact | 目标 Harness / 原生会话的本机联系定位 | Home 的 Contact 数据 |
| CAT Room | 可选跨 Agent 讨论空间 | 独立 CAT 仓库与服务 |

## 关键关系

- Project Registry 只回答项目目录在哪里、哪些 Home 已登记、谁是 Coordinator；不保存项目进度或业务内容。
- Project Vault 通过 INDEX.md 指向当前项目口径；TEAM.md 维护当前成员职责；原始材料和成果留在项目目录。
- 每个长期 Agent 有稳定 Home。换 Runtime 或新建会话不重新分配 Home 身份。
- Rooter 属于安装级，不创建虚构的 Rooter Project。
- TODO v4 是当前责任的唯一原件，包含 Pinned、Current 和 Tasks；任务状态由 Markdown checkbox 表达。
- Mail 是持久输入；Notice 是接收与处理记录。提醒、读取、处理、交付和验收不能合并为一个状态。
- Library 的 Markdown 源文件是权威；Catalog 和搜索结果是派生导航。
- Runtime 与 CAT 是外部协作边界。PAOE 不接管模型推理或 CAT 自身的持久化。

## 历史概念

旧版本的 Project Store、Session 生命周期管理、Work、Cycle、Work Item、Workbench 与旧 Dashboard 属于历史实现或历史设计，不是当前 Portable 的运行对象。历史资料保留供追溯，但不作为新功能的设计依据。
