# PAOE Core

Core 是 PAOE 的**硬基座源码**，负责程序实现与安装机制。各部分的内容按以下职责分别维护：

| 归属 | 保存内容 |
| --- | --- |
| `System/Project-Template/AGENTS.md` | Agent 公共运行规则的唯一母本 |
| `System/Guide/` | 系统操作指导与通信说明 |
| 独立的 Workflow / Skill / Tool 库 | 专业方法与工具目录 |
| 独立项目库 | INDEX、TEAM、AGENTS、成员工位、输入与成果 |
| `Core/` | 命令行入口、文件读写、原生联系与唤醒适配、可选画板及测试 |

专业方法统一保存在独立 Libraries 中，**Core 不再保留 `libraries/` 副本**。
方法库登记只记录原件路径，避免维护第二份正文或误用随包旧版。

## 写入边界：不要污染 Core

**Core 只维护硬基座需要的源码、测试、配置示例和必要开发文档。新增文件前，先确认它确实属于这一职责。**

- 通用运行指南和项目母版放 System 的 Guide、Project-Template；专业 Workflow、Skill、Tool 放独立 Libraries。Core 只引用其入口，不复制正文。
- 业务资料和项目成果放对应项目库；个人 ENTRY、TODO、Mail、Notice 放本人工位；安装维护报告放 Rooter 的 Records。
- 临时下载、过程草稿、一次性排障材料和旧备份不作为长期源码留在 Core；按用途归项目、维护记录或 System 的备份区。
- 完成改动时检查新增文件，移出与硬基座无关的内容，避免重新堆积流程副本、历史报告和临时工具。

现有 `config/local/`、`data/` 是按安装合同使用的本机配置与运行数据区，与受版本控制的源码隔离；不要以“清理 Core”为由删除真实数据。`__pycache__/`、`.pyc` 等自动生成物不属于源码，不纳入 Git 或发布包。

## 安装（Python 3.10 及以上，使用标准库）

`portable.py plan` 显示拟使用的源码与本机数据路径。
先用现有 `paos library init` / `roots set` 入口，在 **Core 之外**准备独立的
Workflow 和 Skill 库，再将本安装指向这些已经初始化的目录：

```sh
python portable.py plan
python portable.py init --workflow-root /absolute/path/to/workflow --skill-root /absolute/path/to/skill
python portable.py doctor
```

已有工具目录时，补上 `--tool-catalog /absolute/path/to/tool-catalog.md`。
工具目录可选，Workflow 和 Skill 库根必填。
`init` 只准备本机安装，不创建或修改外部方法库，也不创建项目或工位文件。
已有安装的库路径通过当前 Library CLI 显式修改，重复执行 `init` 不会重新绑定。

使用已安装的 CLI：

```sh
export PAOS_INSTALLATION_FILE="$PWD/config/local/installation.json"
export PAOS_LIBRARY_ROOTS_CONFIG="$PWD/config/local/library-roots.json"
python code/personal-agent-os/scripts/paos.py --json health
```

Windows PowerShell 使用 `$env:PAOS_INSTALLATION_FILE` 和
`$env:PAOS_LIBRARY_ROOTS_CONFIG` 设置对应的绝对路径。
这两个配置用于**定位本机安装**；项目和成员由各自的登记与原件维护。
`doctor` 只检查安装路径，真实会话、CAT 投递和业务处理需要分别验证。

## 开发与学习

- [源码说明](code/personal-agent-os/README.md)：运行核心 CLI。
- [源码导读](code/personal-agent-os/CODE-TOUR.md)：模块调用链与学习练习。
- [开发准则](code/personal-agent-os/docs/DEVELOPMENT-PRINCIPLES.md)：
  状态归属、冲突保护与测试要求。

```sh
python code/personal-agent-os/scripts/verify.py
node --test tests/board-ui.test.mjs
```

浏览器画板为可选功能，用 `python portable.py serve` 启动。
日常文件操作可直接使用 CLI，无需启动画板或旧 HTTP Dashboard。
Windows 安装、原生唤醒、CAT 接入和项目采用，由 Rooter 分别在实际机器上验证。
