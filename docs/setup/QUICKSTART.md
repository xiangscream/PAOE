# PAOE 快速开始

这份指南负责本机安装与命令入口。先了解各部分的用途，可回到[首页](../../README.md)；配置与资料归属见[系统架构](../../ARCHITECTURE.md)。

## 1. 取得代码并检查配置

需要 Python 3.10+。克隆后进入仓库根目录：

```sh
git clone https://github.com/xiangscream/PAOE.git
cd PAOE
python portable.py plan
python portable.py init
python portable.py doctor
```

`plan` 只读预览，`init` 生成此 checkout 的 `config/local/` 定位配置和必要空目录，`doctor` 只读核对路径。`init` 不覆盖已有配置、不导入项目、不创建工位、不启动服务。

Rooter 是独立的安装级维护工位。如需接入已有 Rooter Home，应先核实身份与 TODO v4，并在**首次 `init`** 时显式传入 `--rooter-home "<Rooter绝对路径>"`。参数以当前版本 `--help` 为准。

克隆得到的是代码与随包方法资产。实际共享库可以独立登记；本机项目、工位、登录态与接收器需分别准备。配置检查通过不代表 Agent 已接续或唤醒已验证。

## 2. 选择当前安装

在仓库根目录设置当前 shell 的安装定位，再检查 CLI：

```powershell
# Windows PowerShell
$env:PAOS_INSTALLATION_FILE = (Resolve-Path .\config\local\installation.json).Path
$env:PAOS_LIBRARY_ROOTS_CONFIG = (Resolve-Path .\config\local\library-roots.json).Path
$env:PYTHONIOENCODING = "utf-8"
python .\code\personal-agent-os\scripts\paos.py health
```

```sh
# Linux / WSL
export PAOS_INSTALLATION_FILE="$PWD/config/local/installation.json"
export PAOS_LIBRARY_ROOTS_CONFIG="$PWD/config/local/library-roots.json"
export PYTHONIOENCODING=utf-8
python code/personal-agent-os/scripts/paos.py health
```

## 3. 接入你选定的项目与工位

先准备真实的项目目录，确认项目编号、现任 Coordinator 和资料组织方式。推荐一个项目对应一个独立 Obsidian 库；需要独立版本历史时，Git 根与项目根保持一致。项目无需嵌入代码仓库或综合资料库。

以下是命令形态：将 `<项目ID>`、`<项目绝对路径>`、`<CoordinatorID>` 换成你的真实值，不要照抄示例创建额外项目。

```text
python code/personal-agent-os/scripts/paos.py project register <项目ID> --root "<项目绝对路径>" --coordinator <CoordinatorID>
python code/personal-agent-os/scripts/paos.py project show <项目ID>
python code/personal-agent-os/scripts/paos.py workstation init <项目ID> <CoordinatorID>
```

项目登记只保存位置、成员和协调者定位，不保存业务进度，也不创建或覆盖工位。`workstation init` 会在项目根补建标准目录，执行前先确认与现有资料组织相容；已有 ENTRY / TODO 应保留。

项目口径从 `INDEX.md` 进入，成员从自己的 `ENTRY.md` 进入。实际 Runtime、Contact、登录和接收器沿对应指南配置；文件投递、原生提醒和 Agent 实际消费分别核验。详见[本机配置指导](PAOE-CENTRAL-CORE-DISTRIBUTED-PROJECTS.md)与[迁移边界](../../MIGRATION-NOTES.md)。

## 4. 可选的人类入口

日常可以直接用 Obsidian 打开独立项目库与共享方法库。需要系统说明总入口时，沿 [System Vault 工具](SYSTEM-VAULT-TOOL.md)先预览、再生成独立说明库；它连接原件，不复制项目和方法正文。

需要画板时，在仓库根运行：

```sh
python portable.py serve
```

浏览器打开 `http://127.0.0.1:8780/`。默认读取此 checkout 的 `config/local/installation.json`。可选 CAT 需显式连接已有服务：

```sh
python portable.py serve --cat-url http://127.0.0.1:8870
```

画板不会自动启动 Runtime、接收器或 CAT；关闭后 CLI 文件操作照常可用。详细操作见[画板说明](../../front/README.md)。

## 名称与开发入口

产品和当前 GitHub 仓库名称为 **PAOE**。命令 `paos.py`、环境变量 `PAOS_*`、持久数据的 `paos-*` schema 以及已有本机目录名称继续保留兼容；不需要为了改名批量迁移资料。

开发前读[仓库约定](../../AGENTS.md)与[学习路线](../../LEARNING-BASELINE.md)。既有检查入口：

```sh
python code/personal-agent-os/scripts/verify.py
node --test tests/board-ui.test.mjs
```

运行产品不需要 Node。自动测试不替代生产工位、原生接续或真实 UI 的采用验证。
