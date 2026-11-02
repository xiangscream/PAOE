# PAOE 当前代码地图

本文只描述 7cd5300 这条 Portable 基线的现行目录和调用关系。不要套用旧版 attention-dashboard-v1-static、local_server、WorkflowService 或 ProjectStore 架构；这些不属于当前正常执行链。

## 1. 仓库分区

~~~text
PAOS-portable/
├─ portable.py                         安装定位助手：plan / init / doctor / serve
├─ config/local/                       本机配置（不提交）
├─ data/                               安装数据根（按安装描述定位）
├─ libraries/workflow/                 随包 Workflow / Guide / Template 示例
├─ front/
│  ├─ paos_front_server.py             可选本地画板后端
│  └─ index.html                       原生 HTML / CSS / JS / SVG
├─ code/personal-agent-os/
│  ├─ scripts/paos.py                  CLI 入口与命令分发
│  ├─ scripts/paos_*.py                领域服务模块
│  ├─ runtime_adapters/                原生 Runtime 接入适配
│  ├─ attention-memory-pipeline-v0/    保留的独立扫描/派生数据管道
│  └─ docs/                            代码说明、合同与历史资料
└─ tests/                              隔离文件、集成与画板测试
~~~

实际安装的 Project Vault、Rooter Home、Workflow / Skill Library 和 Tool Catalog 可以位于仓库之外。仓库中的 config/local、真实业务数据和凭据不应提交。

## 2. 入口

| 入口 | 用途 |
|---|---|
| portable.py plan | 只读查看将生成的本机配置 |
| portable.py init | 创建新的本机安装配置，不创建项目或工位 |
| portable.py doctor | 只读检查配置与路径，不证明业务链路 |
| code/personal-agent-os/scripts/paos.py | 日常 CLI |
| python portable.py serve | 启动可选画板；默认只监听 127.0.0.1 |

CLI 帮助以实际代码为准：

~~~sh
python code/personal-agent-os/scripts/paos.py --help
python code/personal-agent-os/scripts/paos.py library --help
python code/personal-agent-os/scripts/paos.py attention --help
~~~

## 3. 核心模块

| 模块 | 职责 | 学习时关注 |
|---|---|---|
| paos.py | argparse、命令分发、输出与异常出口 | build_parser、execute、main |
| paos_installation.py | installation descriptor 与路径解析 | 配置来源、路径规范化 |
| paos_registry.py | Project 五字段定位登记 | read、register、home-add、原子写入 |
| paos_home.py | Project Home / Rooter Home 定位 | Home ref、身份与路径边界 |
| paos_workstation.py | 工位布局、ENTRY 与工位相关操作 | 路径映射、身份检查 |
| paos_todo.py | TODO v4 解析、渲染和写入 | Pinned / Current / Tasks、指纹与锁 |
| paos_mail.py | 持久 Mail | 消息身份、接收者解析、幂等 |
| paos_notice.py | Notice 读写与处理 | 输入处理状态与来源引用 |
| paos_attention_service.py | Home 状态读面、输入与激活相关操作 | Notice / TODO 的组合边界 |
| paos_contact.py | peers / team / Contact 读面 | TEAM 来源、Contact 事实与未知状态 |
| paos_agent_activation.py | 持久激活意图 | intent 与实际 Runtime 注入分离 |
| paos_wakeup.py | 原生联系目标绑定、状态与触发 | Contact target、一次性调用 |
| runtime_injection.py | Runtime 注入入口 | 适配分发与错误返回 |
| runtime_adapters/ | Codex / OpenCode 等具体接入 | 平台差异留在适配层 |
| paos_library.py | Workflow / Skill Catalog、检索与使用记录 | Markdown 原件与派生索引 |
| paos_cat_cli.py | CAT HTTP 客户端 | 外部系统边界 |
| front/paos_front_server.py | Board 读面与有限动作 | CLI 子进程、错误和结果未知 |
| front/index.html | 画板展示层 | DOM、SVG、事件、HTTP JSON |

## 4. 常见调用链

~~~text
CLI 读操作:
命令行 -> paos.py (build_parser / main / execute)
       -> 目标 paos_*.py 模块 -> installation / registry / home 定位
       -> 读取 JSON 或 Markdown 原件 -> 输出文本或 JSON

TODO 更新:
Agent / Human -> paos.py attention todo-update / todo-write
              -> paos_attention_service.py -> paos_todo.py
              -> 身份校验 -> 指纹 / 锁 / 原子发布 -> TODO.md

发送消息:
Agent / Human -> paos.py agent send
              -> activation / attention service
              -> paos_mail.py 持久化 Mail -> paos_notice.py 登记输入
              -> 可选 Contact / runtime_injection 一次性提醒

画板读取:
Browser index.html -> HTTP JSON -> paos_front_server.py
                   -> Board 读取 Registry / Home / Library
                   -> 必要动作调用 paos.py 子进程 -> JSON -> Browser
~~~

## 5. 按目标找代码

| 想理解或修改 | 从这里开始 |
|---|---|
| 命令参数或帮助文字 | scripts/paos.py 的 build_parser |
| 命令实际做什么 | scripts/paos.py 的 execute 分发及对应模块 |
| Project 如何定位 | scripts/paos_registry.py |
| TODO 如何安全更新 | scripts/paos_todo.py |
| Mail / Notice 如何分工 | scripts/paos_mail.py、paos_notice.py、paos_attention_service.py |
| Agent 如何联系另一个 Home | scripts/paos_contact.py、paos_agent_activation.py、paos_wakeup.py |
| Runtime 提醒如何适配 | scripts/runtime_injection.py、runtime_adapters/ |
| Workflow / Skill 如何检索 | scripts/paos_library.py |
| 画板如何展示系统 | front/paos_front_server.py、front/index.html |
| 自动测试在哪里 | tests/、scripts/verify.py |

## 6. 阅读与修改纪律

- 先读根目录 ARCHITECTURE.md、AGENTS.md 和 DEVELOPMENT-PRINCIPLES.md，再读具体模块。
- 先沿调用链找到现有写者，不在 CLI、前端或新模块里复制第二套写入逻辑。
- 普通读操作优先用临时 fixture；不要为了学习读取或改写真实生产 Home。
- 修改核心合同、路径或持久写入时，先理解其调用者和测试；不要只看单个函数。
- 当前实现与本页不一致时，以代码为准，并修订本地图，不新增相互矛盾的解释。
