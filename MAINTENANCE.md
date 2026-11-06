# 本机维护

<!-- paoe:human-intro:start -->
> 需要查安装、排查打不开的入口或安排备份时，从这里定位。具体运行恢复由 Rooter 处理。
<!-- paoe:human-intro:end -->

<!-- paoe:agent-reference -->
## 操作与参考

## 当前安装

| 内容 | 准确入口 |
| --- | --- |
| 硬基座代码 | [Core](Core/) |
| 程序源码 | [Source](Core/code/personal-agent-os/) |
| 安装描述 | 本机 `PAOS_INSTALLATION_FILE`；新安装默认为 `Core/config/local/installation.json` |
| 方法库登记 | 安装描述中的 `library_roots_config` |
| 安装数据与 Registry | 安装描述中的 `data_root` |
| 维护者工位 | [Rooter 公共入口](rooter/README.md)；实际 ENTRY/TODO 位于登记的 `rooter_home` |
| 维护成果与历史记录 | `rooter_home/Records/` |

准确版本以 `health` 与 Core 实际 checkout 为准；接受与采用证据保存在对应维护记录，不能默认本机与 GitHub main 相同。

```powershell
python -X utf8 -B Core/code/personal-agent-os/scripts/paos.py --installation-file Core/config/local/installation.json health
python -X utf8 -B Core/code/personal-agent-os/scripts/paos.py --installation-file Core/config/local/installation.json install show
```

installation.json 的 source_root、data_root、library_roots_config、rooter_home 分别定位程序、安装数据、方法登记和 Rooter 工位。配置修改沿现有 CLI、schema 与当前授权执行。

以上命令在 System 根目录执行；已有机器将参数替换为自己的权威安装描述，避免创建第二套配置。

## 遇到问题找谁

| 现象 | 处理入口 |
| --- | --- |
| 项目目标、业务口径或分工不清楚 | 对应项目 INDEX 与 Coordinator，见[项目与 Agent](PROJECTS.md)。 |
| 文件或目录打不开 | 保留原路径和错误，先核磁盘、实际文件与登记，再交对应负责人处理。 |
| Agent 没有响应，安装或原生连接异常 | [Rooter 入口](rooter/README.md)及[运行维护规则](Guide/guide-rooter-installation.md)。 |
| 需要唤醒某位 Agent | [汇总页的完整唤醒命令](PROJECTS.md#外部唤醒)。 |

Home 保存工作，Harness 执行模型，Contact 连接已绑定会话。配置存在、提醒受理、本人实读和任务完成分别核实；自动恢复须由本机实际验收。

成员职责或TEAM变更后，用现有汇总器更新本机PROJECTS，不手工另维护一份名册。在System根运行：`python Core/code/personal-agent-os/scripts/paos_team_overview.py --installation-file <本机安装描述> --output PROJECTS.md --write`。改为`--check`只核是否过期；生成的机器路径不纳入公共发布。

文件不可用时核准确原件，不从空结果推断项目不存在；保留原登记、处理缺盘或读取错误。普通文件操作不依赖旧 Core/Bridge 或 Dashboard。

## 备份与记录

- System 备份覆盖 Core、Rooter、规则与母版。独立 Libraries、项目库及宿主 Runtime/凭据分别保护。
- Rooter 的维护报告集中在 `rooter/Records/`；当前行动只维护在本人 TODO。
- 旧安装、导航原页与退出使用的备份放在 `.backups/`。移动映射与哈希见对应维护记录。
- 回退前先保护新输入和未提交修改，再核准确配置与作用范围，保留历史证据。

## 可选界面与学习

[CAT](CAT/README.md) 是否可用按本机配置核对。可选 Board 从 `Core` 目录用 `python portable.py serve` 启动，默认地址为 [127.0.0.1:8780](http://127.0.0.1:8780/)；参数查当前 `serve --help`，本页不代表服务已运行。

[学习路线](Learning/ROADMAP.md) · [个人笔记](Learning/NOTES/README.md)

需要追代码时，从 Source 的 `scripts/paos.py` 沿 Registry、Home、TODO、Mail/Notice、Library 与 Contact 模块追一条实际调用。远端[学习基线](https://github.com/xiangscream/PAOS-portable/blob/b8d6263e4da7b045c48a6bb2acbd4230d83c653a/LEARNING-BASELINE.md)说明的是文档版本；本机执行版本读实际安装。
