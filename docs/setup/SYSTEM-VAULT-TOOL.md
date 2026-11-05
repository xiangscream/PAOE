# System Vault 配置工具

本工具把已有安装的真实路径连接成可读的 Obsidian 说明库。它只读 Installation、Library roots 和 Project Registry；不复制项目/方法正文，不读取私有 Mail，不修改任何领域原件，也不登记 Obsidian、安装插件或启动服务。

设计范围见[配置指导 PR #9](https://github.com/xiangscream/PAOS-portable/pull/9)：本轮建立中央 System Vault，不迁移现有项目或拆分其 Git 历史。

## 预览和首次生成

从本仓库运行，所有路径换成实际安装和一个**不存在的新目标**：

```text
python tools/system_vault.py --installation-file <当前installation.json> --output <新System-Vault目录>
```

默认只显示计划，不写文件。核对后追加 `--apply`。如需显式覆盖该安装的库登记，使用 `--library-roots-config <当前库登记文件>`；默认以传入的安装描述为准，不采用另一安装的环境变量。

工具拒绝现有的未知目录、原件所在目录及其父子路径。首次先生成相邻候选，再发布到新目标；失败候选不会自动清理用户目录。生成完成后在 Obsidian 的“打开文件夹为仓库”中选择新目录，打开 HOME.md。不需要社区插件。

## 人工页与快照

每页标题下方有“给使用者”说明，先用白话解释用途和使用入口；后面的“操作与参考”保留精简的定位、命令和规则。Agent可跳过 `paoe:human-intro:start` 至 `paoe:human-intro:end`，从 `paoe:agent-reference` 继续。人类说明只帮助理解，执行条件和必要事实仍在后文。Frontmatter仍位于文件最前面。

- HOME、架构/操作解释、学习笔记可以正常手改；再次运行不覆盖已有人工页。
- 四份带来源和时间的定位快照分别位于 Installation、Projects、Agents、Libraries，只有明确追加 `--refresh-snapshots --apply` 才刷新。
- 快照若被人工修改，工具在写入前拒绝覆盖；把需要保留的补充移到普通说明页，审阅后再处理。没有 force 覆盖开关。
- Registry 缺盘记录保留为 Unavailable，绝不从导航刷新触发创建/移动/注销项目。
- data_root或Registry根目录不可读时明确报错，不生成“零项目”快照；只有已初始化、可读取且确实为空的Registry才显示零条登记。

快照只提供定位和存在性。Obsidian URI 是候选，需在本机实际打开验证；跨库原件所属目录若未登记为 Vault，使用准确文件路径和外部编辑器。不能把“链接语法正确”当作“UI已打开”。

## 验证

```text
python -m unittest discover -s tests -p test_system_vault.py -v
python code/personal-agent-os/scripts/verify.py
```

隔离测试覆盖旧原件不变、人工修改保留、已有目录拒绝、不同绝对项目根/缺盘保留、Registry根不可用、URI编码和导航目标。不同绝对根路径使用临时目录模拟，不是实际卸载Windows盘符或WSL挂载，不证明操作系统映射。它不等于生产 Obsidian 采用，实际UI导航需单独观察。工具不修改既有CLI参数、schema、Runtime或业务流程。
