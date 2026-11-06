# Rooter · 安装级维护入口

Rooter 维护本机安装、共享入口和运行连接，不属于任何 Project。公共工作规则读 [AGENTS 母本公共区](../Project-Template/AGENTS.md)，安装与恢复按 [Rooter 指南](../Guide/guide-rooter-installation.md)。

## 公共文件与本机实例

本 README 是发布原件。实际 `ENTRY.md`、`TODO.md`、Contact、Mail、Notice、Records 和原生绑定属于本机实例，不进入发布包。

- 已有 Rooter：保留身份、工位和历史；由安装描述的 `rooter_home` 定位，不要求为了目录一致搬家。
- 尚无 Rooter：`portable init` 不创建身份或工位。由本机维护者按现有 Home/TODO v4 合同准备，再显式登记；不复制别人的 Thread、凭据或 STOP。
- 恢复工作：实读适用的全局 AGENTS、本人 ENTRY/TODO、公共运行正文、Rooter 指南和当前原输入；专题按实际任务读取。
- 本人只维护自己的行动；项目目标与成员职责归对应 Coordinator 和 TEAM。

## 本机操作

在 System 根目录执行，先核准确安装：

```text
python -X utf8 -B Core/code/personal-agent-os/scripts/paos.py --installation-file Core/config/local/installation.json install show
python -X utf8 -B Core/code/personal-agent-os/scripts/paos.py --installation-file Core/config/local/installation.json health
```

已有机器继续使用自己的权威安装描述；不要把示例路径当成第二套配置。进入 `rooter_home` 后用 `python contact.py status` 查本人的联系状态；TODO 由 `attention rooter-todo-update` / `rooter-todo-write` 和指纹守卫维护。

配置、消息投递、提醒受理、实际消费各自核实。Codex 接收器与 OpenCode 适配的代码在 Core；项目母版 notices 下的脚本只支持项目 Home，不能直接当作 Rooter 启动器。

## 更新公共原件

只改本次涉及的段落，保留人工实例内容。路径、命令和字段变化同步直接使用方；PROJECTS 用正式生成器重建，公共 AGENTS 只更新受管理公共区。具体边界见 [关联更新](../Guide/guide-project-work-world.md#关联更新)。
