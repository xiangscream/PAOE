# 采用固定 System 基线

本页用于已有机器升级。先取得已冻结的 ZIP 或离线 Git Bundle，核对 `RELEASE.md`、两个源码提交和校验哈希。公开旧 main、审阅快照和本机运行目录都不能代替发布源。

## 保留边界

保留本机安装数据、Registry、Rooter/项目 ENTRY 与 TODO、Mail/Notice、Contact、Session、模型、STOP、Libraries、业务资料和 Obsidian 配置。只采用新代码与公共规则；不因模板变化重建身份或覆盖工位。

Rooter 公共入口是 `rooter/README.md`；实例由本机安装描述定位。发布中的 `PROJECTS.md` 是中性入口，实际成员页仍由本机 Registry、TEAM、ENTRY 生成。

## 实施顺序

1. **盘点与备份。** 记录正在使用的安装描述、source/data/library/rooter 路径、Git 状态及在途操作；保护原件、人工编辑和真实进程，不按 Python 进程名批量停止服务。
2. **独立展开版本。** 解压到新目录，或从 Bundle clone 并 checkout 指定 tag；先运行完整 verifier 与本机路径检查，不直接覆盖旧安装。
3. **核数据合同。** 用新 CLI 显式读取本机安装与工位。Registry 必须符合当前 `paos-project-registry/v1`，TODO 使用 v4；不兼容时保留原件并由本机 Owner 处理，不能用空登记或新 TODO 代替历史。
4. **显式切换代码定位。** 按同版 `install configure --help` 修改本机选定的安装描述，保留自己的 data_root、库登记、rooter_home、编号与 Runtime。切换前明确哪些入口读取该描述；原 Contact 的默认安装定位和 shell 包装器也须一致。不要同时留两份自称权威的配置。
5. **合并公共规则。** AGENTS 公共区用现有 diff/apply/check，保留人工项目约定；既有 ENTRY、INDEX、TEAM、TODO 只合并相关段落。新工位的 notices 文件与 ONBOARD 仍按母版创建步骤补齐，不追加入职给历史成员。
6. **真实接续与回退。** 核原 Home/Session/模型/STOP，运行 `health`、`install show` 和本机 `contact.py status`；选一条真实工作验证 Mail、Notice、本人实读、TODO 和回告。失败时保留新增输入，按备份恢复旧代码定位；不重置数据或重投结果未知的消息。

`Core/portable.py doctor` 检查本 checkout 的本地配置对；已有安装描述位于其它位置时，用新 CLI 的显式 `--installation-file` 核对实际安装，不把另一份空配置当升级成功。

## 数据根保持独立

代码可以切到新 checkout，已登记的绝对 data_root 可以继续指向原数据目录。doctor 与重复 init 只校验该目录已存在，不创建、搬运或修复包外数据；source_root 与本地库配置定位仍受当前 checkout 约束。

## 完成口径

源码校验、Windows 隔离重建、ASUS 本机采用、旧电脑采用分别记录。CAT、自动冷启动和其它外部授权按真实结果注明。两台机器确认采用后，再整体同步 GitHub；本页不触发 GitHub 发布或迁移 Git 历史。
