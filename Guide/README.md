# Guide · System 专项操作指南

从所属项目的 `AGENTS.md` 公共区读取生效的运行规则。公共区由[项目母版](../Project-Template/AGENTS.md)分发。遇到具体操作时，按下表打开相应指南。

---

## 专题指南索引

### 1. 业务与资源按需定位

| 场景 | 指南入口 | 核心内容 |
| --- | --- | --- |
| 库的阅读网络、价值取舍、批量整理与 Git | [库组织与项目文件](guide-project-work-world.md) | 渐进阅读、主题关系、TODO收尾、历史退出与文本版本 |
| 按任务查找专业方法、技能与本机工具 | [工作入口与资源检索](guide-work-method.md) | `paos library search` 与 Tool Catalog 核验原则 |
| 快速查找 CLI 前缀、Contact 与运维入口 | [操作入口速查](ops-entry.md) | 常用运维命令、公开联系包生成与状态检查 |

### 2. 协同、通信与接班

| 场景 | 指南入口 | 核心内容 |
| --- | --- | --- |
| 成员间 Mail、Notice、CAT、Wake 通信实操 | [通信操作](guide-paos-cat-operations.md) | 持久邮件投递、通知处理生命周期与断点排查 |
| 任务完成后的普通输入清理 | [输入收尾](input-cleanup.md) | 完成出口接清理、保留原话、删除后同 ID 不重投 |
| 会话压缩、接班与在途输入接续 | [Runtime 接班](guide-runtime-handoff.md) | 压缩前状态固化、薄状态恢复与新旧会话平滑接力 |
| Coordinator 总体安排、方向与跨组协调 | [Coordinator 工作循环](wf-coordinator-governance-cycle.md) | 优先级管理、阻碍拔除、依赖对齐与阶段收口 |
| 跨机协作、两机采用与经历同步 | [跨机协作](guide-cross-machine-experience.md) | 跨机员工联系、资料同步维护与经历库刷新 |

### 3. 系统维护、升级与安装

| 场景 | 指南入口 | 核心内容 |
| --- | --- | --- |
| CLI 接口参数、返回格式与状态契约 | [接口参考](guide-paos-interface-reference.md) | CLI 返回协议、错误码与调用契约 |
| 本机工具行为差异、排障与陷阱 | [工具陷阱](guide-tool-pitfalls.md) | WSL/Windows 路径差异、编码、文件移动操作要点 |
| 软流程分发、版本发布与升级采用 | [升级采用](guide-upgrade-adoption.md) | 公共区同步指纹检查、发布公告与回退机制 |
| Rooter 安装管理、全局恢复与维修 | [Rooter 安装](guide-rooter-installation.md) | 系统级工位维护、母本发布与机器环境支持 |
| 夜间整理与自动维护 | [夜间整理](wf-night-maintenance.md) | 非侵入式库卫生巡检与状态汇总 |
| 消息与公告标准样板 | [Templates](Templates/README.md) | 采用公告等标准格式参考 |

---

## 边界与说明

- **Guide 的定位**：说明“在什么业务场景使用什么具体工具或步骤”。
- **协议唯一性**：CLI/Mail/Notice/Wake 等硬接口的具体参数与状态定义由自身 `--help` 和代码实现保障，Guide 不另造私有协议。
- **专业方法归属**：通用专业技能与行业工作流收录于独立 Libraries，不堆积在 System Guide。
