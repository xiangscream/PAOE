# 安装、配置与升级

第一次在一台电脑使用 PAOE，先判断它是否已经装好。已有安装直接从本机 CLI 进入。准备新机器或替换已有版本时，再进入下面对应的一节。

## 已安装机器上的首次使用

标准 Windows 安装在 PowerShell 运行以下两条命令。第一条给出本机实际的源码、数据、方法库和 Rooter 工位位置，第二条检查安装是否可读。

```powershell
& "$env:USERPROFILE\.paos\bin\paos.cmd" install show
& "$env:USERPROFILE\.paos\bin\paos.cmd" health
```

文中的 `paos` 表示这台机器已部署的命令入口。已有员工用本人 ENTRY、AGENTS 和 TODO 恢复工作。临时协作者从名册找接收者，按获准的项目范围留信。需要长期负责项目时，由 Coordinator 和 Rooter 办理入职。

[项目与同事](PROJECTS.md) · [外部协作](Guide/ops-entry.md#外部-agent-临时协作) · [项目与工位入职](Project-Template/README.md#新项目和工位的创建)

## 新机器安装

从 [System 发布页](https://github.com/xiangscream/PAOE/releases)取得固定版本的 ZIP、`.zip.sha256` 和 `FILES.json`。按同版清单核对后解压。准备好现有 Workflow 和 Skill 库的绝对路径，在 Windows 的 System 根目录使用 Python 3.10 或以上版本运行。

```text
python Core/portable.py plan
python Core/portable.py init --workflow-root <Workflow库绝对路径> --skill-root <Skill库绝对路径>
python Core/portable.py doctor
python -X utf8 -B Core/code/personal-agent-os/scripts/paos.py --installation-file Core/config/local/installation.json health
```

这一步建立本机配置和空安装数据。已有 Rooter 工位可通过 `--rooter-home` 指定实际绝对路径。新项目、员工及其原生会话按入职流程分别登记。外置数据根由维护者事先定位，`doctor` 检查当前 checkout 的配置。已有安装用它自己的安装描述核对。

## 已有机器升级

1. 从 `install show` 记录本机正在用的安装描述和库位置。保存本机改动、人工批注与在途任务。保全项目登记、工位、TODO、通信、会话、绑定、STOP、凭据和 Obsidian 配置。
2. 将指定 tag 的包单独展开并校验。离线交付可按同一 tag 从 Git Bundle 取得。读 `VERSION` 和 `SOURCE.lock.json` 确认 System 版本和 Core 来源。
3. 用新 CLI 显式读取原安装描述，核对登记的项目、工位与 TODO。若新版改变数据格式，先用该版迁移说明检查原数据并保存恢复位置。
4. 按 `paos install configure --help` 切换代码定位。沿用本机的数据根、Rooter 工位和库登记。若新 checkout 自带配置，配置中的库路径仍指向原独立 Libraries。桌面入口、CLI 与 Contact 应使用同一安装描述。
5. 按正式模板的差异合并公共运行规则，保留项目约定、工位正文及 Human 的编辑。重新生成本机项目名册。公共区的具体命令见[公共规则分发](Guide/guide-upgrade-adoption.md#公共区统一分发system-agents)。
6. 从原会话接一项真实工作，确认能读原任务、联系所需同事并把成果交回。需要回退时，先保全切换后新增的输入，再恢复原代码与定位。

## 版本和资料从哪里来

| 内容 | 来源和维护方式 |
| --- | --- |
| System | [公共源码](https://github.com/xiangscream/PAOE)和[固定发布版本](https://github.com/xiangscream/PAOE/releases)。开发通过分支和 PR 合入，安装使用指定 tag。 |
| Libraries | [独立方法库](https://github.com/xiangscream/PAOE-Libraries)。采用已发布的工作流与技能，按该库说明登记本机位置、更新目录。 |
| 项目和经历 | 项目业务由各项目维护。两机按约定范围同步经历正文和团队资料，协作方式见[跨机指南](Guide/guide-cross-machine-experience.md)。 |
| 本机运行数据 | 安装描述指定本机数据根。工位联系配置、账号、会话、凭据与本机历史在各机分别维护。 |

发布者从指定 Git 版本构建包，`VERSION` 标识 System 版本，`SOURCE.lock.json` 固定 Core 源提交和树。发布工具从完整 System Git 树取文件，同一 tag 可复现同一 ZIP。

```text
python release.py build --ref <固定tag> --output <输出目录>
python release.py verify <发布ZIP>
```

运行中的安装、连接、备份和故障恢复可直接查[本机维护](MAINTENANCE.md)和[Rooter 安装维护](Guide/guide-rooter-installation.md)。
