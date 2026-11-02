# PAOE 学习基线

## 基线定义

- **核心业务代码基线：** 7cd530029db1c95cf4dd01bb0b9e8a9df2421f31
- **仓库：** xiangscream/PAOS-portable
- **产品名称：** PAOE（Personal Agent Operating Environment）
- **兼容标识：** CLI 仍为 paos.py，环境变量仍为 PAOS_*，schema 仍使用 paos-*，仓库名暂不变。
- **本轮整理范围：** 架构说明、领域模型、代码地图、导航、历史归档与画板显示名称；不修改业务逻辑、持久 schema、真实工位或本机安装。

本轮在该业务行为基线上只增加文档导航、注释/显示名称和相应测试断言，不改变业务逻辑或持久格式。PR #8 合并后的 main 是完整学习 checkout；学习时以 main 中的文档为入口，以这里列出的提交作为业务行为参照。后续功能改动应另起提交，不混入这轮学习基线整理。

## 学习约定

1. 先读原件和测试，再读解释；代码与测试不一致时，以实际代码为准。
2. 从隔离 fixture 学习，不用真实生产 Home 做练习。
3. 每次只学习一条完整调用链，先能解释，再做小改动。
4. 不为了学习顺手重构，不改业务 schema，不清理生产数据。
5. 每个练习保留：目标、入口、输入、调用链、写入原件、失败行为、测试。

## M0–M7 路线

| 阶段 | 主题 | 首要材料 | 阶段产出 |
|---|---|---|---|
| M0 | 系统全貌 | README、ARCHITECTURE、DOMAIN-MODEL | 能画出系统图，解释五类事实的归属 |
| M1 | 文件与数据模型 | paos_registry.py、paos_home.py、paos_todo.py | 能读懂 Project Registry 与一个 TODO v4 |
| M2 | Python 软件结构 | paos.py、paos_installation.py、paos_attention_service.py | 能追踪 CLI 参数到领域模块 |
| M3 | 消息与状态 | paos_mail.py、paos_notice.py、paos_agent_activation.py | 能解释 Mail → Notice → Reminder → Handle 的区别 |
| M4 | Runtime 接入 | paos_contact.py、paos_wakeup.py、runtime_injection.py、runtime_adapters/ | 能说明 PAOE 与 Harness 的边界 |
| M5 | Workflow / Skill / Tool | paos_library.py、libraries/workflow/ | 能找到方法原件并解释 Catalog 为什么是派生物 |
| M6 | 前端 | front/paos_front_server.py、front/index.html、tests/test_board.py | 能追踪一次页面读取和一次动作请求 |
| M7 | 工程交付 | tests/、scripts/verify.py、Git 分支与 PR | 独立完成一个小型 Spec → Test → Code → Review |

## 推荐第一轮顺序

1. 根 README：只读产品定位和安装边界。
2. 根 ARCHITECTURE：理解系统图与事实归属。
3. DOMAIN-MODEL：区分 Registry、Vault、Home、Library、Runtime。
4. CODE-MAP：按目标定位实现文件。
5. DEVELOPMENT-PRINCIPLES：理解为什么不增加不必要的机制。
6. tests/test_headless.py 与 tests/test_todo.py：从隔离 fixture 看系统如何验证文件合同。
7. 最后再看 front/README.md 与 tests/test_board.py。

## 先跑什么

只读检查：

~~~sh
python portable.py plan
python portable.py doctor
python code/personal-agent-os/scripts/paos.py --help
~~~

隔离测试：

~~~sh
python code/personal-agent-os/scripts/verify.py
node --test tests/board-ui.test.mjs
~~~

启动画板是可选项；它需要本机安装配置和真实项目登记，不是学习 CLI 或 Python 模块的前置条件。

## 暂不纳入第一轮学习

- 旧 docs/planning 中的历史架构评审包。
- 旧 ProjectStore / Work / Cycle / Session 管理链。
- 真实生产 Contact、Runtime UUID、接收器进程和原生会话。
- attention-memory-pipeline-v0 的内部细节，除非后续专门学习数据管道。
- 为了“全面掌握”而一次性阅读所有历史 handoff、patch 与旧测试。

目标是掌握一条真实端到端链路，再逐步扩展，而不是读完整个仓库才开始动手。
