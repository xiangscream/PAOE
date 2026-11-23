# 安装级机器 Store：显式迁移与回退

业务 Mail/Notice、TODO/ENTRY、项目原件留在原 Home。Contact 集中到安装 Data/contact/native-targets.json；dispatch 按发送方作用域放 Data/mail/project-ID/dispatch 或 Data/mail/rooter/dispatch；项目布局放 Data/ui/project-ID/board.json。

此切片提供独立 CLI 子模块。总 CLI 集成前可在候选 scripts 下运行：

```text
python paos_data_cli.py --installation-file INSTALL data migrate plan
python paos_data_cli.py --installation-file INSTALL data migrate execute --before-state RECEIPT
python paos_data_cli.py --installation-file INSTALL data migrate rollback --before-state RECEIPT
```

`plan` 只读；目标已存在则拒绝覆盖，不推测它是哪次迁移。执行前暂停受影响机器 Store 的全部写入者，保存现场；本工具不负责暂停进程或切换生产代码。迁移与回退过程中保持同一写入冻结，不让旧、新版本并发写。

`execute` 先备份旧文件并持久化 RECEIPT，然后发布合并 Contact、移动 dispatch 与 UI。重放同一 RECEIPT 不覆盖迁移后新增数据；中途失败用同一 RECEIPT 接续已完成移动。备份尚未完成时源 Store 未改；备份目录冲突需要先检查该次失败，不能覆盖重建。

`rollback` 先保留整个新 Contact 和各作用域 dispatch/UI 快照，再将**当前**记录带回旧位置。旧 key 的删除保留为删除，改过的绑定/布局保留当前值，新 key 按既有来源、登记 Home 或明确 project_id 返回所属旧 Store。无法确定新绑定归属时先报错，Data 留在原处。旧目录又出现或旧 Contact 被修改时也报冲突，避免覆盖另一写入者。回退中断沿同一 RECEIPT 接续；已回退重放不再写原件。

Contact 原副本在迁移后保留为回退依据，但正式新读写不得再读它。低层函数暂保留无安装参数的旧接口供独立旧调用测试；**正式 CLI 必须传已解析 installation_path，生成的 contact.py 也显式传入本人 INSTALLATION_FILE。** 完整生产采用必须包含总 CLI 接线与重新生成/核对已安装 Contact 入口，不能只替换路径函数。

全局 Contact 的原会话匹配只扫描安装 Store 一次，再按登记项目 Home 过滤，Rooter 单列，不因扫描五个项目而把同一个会话误判成多份。本人准备仍受 Thread/STOP 和原环境约束，不因迁移重建身份或切模型。

主 CLI 接线：导入 `add_data_parsers, execute_data`；在顶层 subparsers 调用前者；command==data 时调用后者并传 resolved_installation_path。所有 Contact、Mail 发送/状态/激活/跟踪、团队读面的原调用点均须传安装描述。作者交接提供精确调用清单，不修改 S010 单写的 paos.py。

验证：Core/tests/test_data_paths_migration.py 使用五个合成项目与 Rooter，测试只读计划、CLI重放、中断接续、跨作用域同消息ID、切换后新增/修改/删除与回退快照、冲突不写。接收准备和前端布局继续用已有回归。生产迁移仍由 Rooter 以独审通过的配对版本执行。
