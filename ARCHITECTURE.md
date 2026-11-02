# PAOE 架构与事实边界

本文描述 PAOE 当前实现，基于代码学习基线 7cd5300。仓库名、CLI 与历史 schema 仍保留 PAOS 字样；产品名称为 PAOE。代码入口见 [当前代码地图](code/personal-agent-os/docs/CODE-MAP.md)，安装方式见 [README](README.md)。

## 1. 系统定位

PAOE 是运行在个人电脑上的 Agent 工作环境。它不负责替模型思考，也不接管 Harness 内部运行状态；它保存可以跨会话、模型与 Runtime 延续的工作事实，并提供稳定的文件与命令入口。

核心职责：定位 Project Vault、固定 Agent Home、共享方法库和本机安装；保存 Agent 当前责任、持久输入与处理事实；提供 Workflow / Skill / Tool 发现入口；在显式配置时通过 Contact、Runtime Adapter 或外部 CAT 请求一次提醒或协作。

PAOE 不是 Harness，不是后台 Agent 调度平台，也不是完整项目管理 SaaS。

## 2. 总体结构

~~~mermaid
flowchart TB
  Human[Human] --> Runtime[Agent Runtime / Harness]
  Runtime --> CLI[PAOE CLI: paos.py]
  Library[Workflow / Skill / Tool] -.方法参考.-> Runtime
  CLI --> Install[Installation Descriptor]
  CLI --> Registry[Project Registry: locator only]
  Registry --> Vault[Project Vault]
  Vault --> Home[Agent Home: ENTRY / TODO / Mail / Notice]
  CLI --> Home
  CLI --> Contact[Contact / Wake]
  Contact --> Adapter[Runtime Injection Adapter]
  Adapter --> Runtime
  CLI -.optional HTTP.-> CAT[External CAT]
  Board[Optional Board UI] --> Server[Local Python HTTP Server]
  Server --> CLI
  Server --> Vault
~~~

这是职责图，不表示每台机器都已配置所有连接。Project/Home/Library 本地文件操作不要求 CAT、画板或 Runtime 在线。

## 3. 四类核心资产

### Installation：本机定位

portable.py 管理本机安装定位：installation.json 保存源码根、数据根、Library roots 配置和可选 Rooter / 编号登记路径；library-roots.json 保存 Workflow、Skill、Tool Catalog 的权威位置。它们是机器级配置，不是业务事实。

### Project Registry：只负责定位

单条记录 schema 为 paos-project-registry/v1，只有 schema、id、root_path、homes、coordinator_home_id 五个字段。它不是 Project 数据库，不保存项目摘要、任务、成果或进度。

Project Vault 才是业务事实所在。INDEX.md 是项目导航与口径入口；TEAM.md 记录当前成员职责；材料、决策、成果和 Git 历史留在项目自己的目录中。

### Agent Home：长期责任与输入

Project Agent Home 位于 Project Vault 的 Workstations/<home-id>/；Rooter 是独立的安装级 Home，不属于任何 Project。

- ENTRY.md：身份、固定入口、安装与共享指南定位。
- TODO.md：唯一当前责任文件，现行合同为 paos-todo/v4。
- mailbox/：持久 Mail 原件。
- notices/：输入登记与处理事实。
- Contact：本机 Runtime 联系目标；配置存在不代表在线或已接手。

TODO v4 包含 Pinned（自由 Markdown）、Current（当前目标、下一步、等待与引用）和 Tasks（原生 Markdown checkbox）。结构化写入走现有 Home 写者并受指纹、锁和原子发布保护。

### Shared Library：可复用方法

Workflow 是多步流程与通用指南；Skill 是专业方法；Tool Catalog 描述工具用途和入口。Markdown 源文件是权威，Catalog / 搜索结果是派生导航。工具目录存在不等于当前机器已安装、已授权或可调用。

## 4. 主要工作链

恢复：Harness 启动 Agent → 读取 ENTRY → 读取工作循环与必要角色指南 → 读取 TODO → 实读当前输入与成果引用 → 继续已授权的下一步。

委派：agent send → Mail 持久化 → Notice 登记 → 可选 Contact 原生提醒 → Agent 实际读取 → Notice 处理 → Agent 更新 TODO / 项目成果 → Human 或约定负责人验收。

Mail 已保存不等于提醒受理；提醒受理不等于 Agent 已读取；Notice handled 不等于任务完成；Task done 不等于 Human 已验收。结果未知时先核对原件，不盲目重发。

资源发现：沿共享 Workflow 指南检索 Workflow / Skill / Tool；专业求助沿 TEAM / peers 找 Home，再用现有 agent send 联系。不新增通讯录、调度器或自动推荐引擎。

## 5. CLI 与领域模块

日常程序入口是 code/personal-agent-os/scripts/paos.py。它负责参数解析、命令分发、结果输出和错误出口；具体业务由 paos_*.py 模块负责。

| 领域 | 模块 | 职责 |
|---|---|---|
| 安装与路径 | paos_installation.py | 安装描述、路径解析 |
| Project 定位 | paos_registry.py | 五字段 Project Registry |
| Home 定位 | paos_home.py | Project Home / Rooter Home |
| 工位合同 | paos_workstation.py、paos_todo.py | 工位定位、TODO v4 |
| 输入处理 | paos_mail.py、paos_notice.py、paos_attention_service.py | Mail、Notice、Home 当前状态 |
| 联系与激活 | paos_contact.py、paos_agent_activation.py、paos_wakeup.py | Contact、激活意图与唤醒入口 |
| Runtime 接入 | runtime_injection.py、runtime_adapters/ | 显式原生提醒适配 |
| 方法库 | paos_library.py | Workflow / Skill / Tool 搜索与目录 |
| CAT | paos_cat_cli.py、paos_cat_activation.py | 对独立 CAT 服务的可选调用 |

CAT 是外部组件，不包含在本仓库。普通文件操作不依赖 CAT HTTP 服务。

## 6. 可选画板前端

front/paos_front_server.py 使用 Python 标准库提供仅绑定 127.0.0.1 的本地 HTTP 服务；它读取安装、Project、Home 和 Library，需要执行既有动作时调用 PAOE CLI。front/index.html 使用原生 HTML / CSS / JavaScript / SVG。

前端只负责展示和交互，不另建业务状态或 Home 写者。Agent 节点来自 Registry；当前责任来自 TODO；项目口径来自 INDEX；CAT 房间事实由外部 CAT 保存。节点拖动和连线是画板视图，不是持久组织关系。关闭画板不影响 CLI 文件操作。

## 7. 明确不做的事

- 不复制 Project Vault 的业务事实到第二个状态数据库。
- 不接管 Codex / OpenCode 等 Harness 的内部会话状态。
- 不以文件存在、PID 或 Contact 配置推断 Agent 在线或已接手。
- 不强制每个任务拆成多个 Agent。
- 不为个人单机系统预建多用户权限、分布式锁或后台调度平台。
- 不把前端变成另一套任务编辑与状态写入系统。

## 8. 验证边界

~~~sh
python code/personal-agent-os/scripts/verify.py
node --test tests/board-ui.test.mjs
~~~

前者覆盖隔离文件、CLI、核心模块、接收器模拟和语法检查；后者覆盖少量前端纯逻辑。它们不证明真实 Project 已迁入、不证明生产 Runtime 在线，也不替代本机采用后的业务观察。生产采用另按 [迁移说明](MIGRATION-NOTES.md) 处理；学习入口见 [LEARNING-BASELINE.md](LEARNING-BASELINE.md)。
