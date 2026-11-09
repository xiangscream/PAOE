# PAOE-System

完整的 Agent 工作环境公共基线：Core 提供硬基座，Guide 提供专项操作，Project-Template 提供完整项目母版，rooter 提供安装级公共入口。

从 [HOME](HOME.md) 使用系统，从 [SYSTEM](SYSTEM.md) 理解职责。专业方法保存在独立 Libraries，业务与成员工位保存在独立 Project Vault。

## 已安装机器上的首次使用

先使用本机已部署的命令入口。标准 Windows 安装的入口在当前用户目录，下面的命令不依赖工作目录或已有员工 Home：

```powershell
& "$env:USERPROFILE\.paos\bin\paos.cmd" install show
& "$env:USERPROFILE\.paos\bin\paos.cmd" health
```

下文的`paos`表示这份完整调用前缀；已加入PATH时可直接写`paos`。其它部署方式使用本机维护者公布的入口。包内`Core/config/local/`属于下面“新安装”生成的配置，不能拿它覆盖已有入口选择的安装和库配置。

| 当前身份 | 接下来做什么 |
| --- | --- |
| 已有员工Home | 从本人ENTRY、AGENTS、TODO和当前输入恢复原责任。 |
| 临时外部协作者，没有Home | 从[项目与同事](PROJECTS.md)找到本次获准工作的项目及接收者，按[联络入口](Guide/ops-entry.md#外部-agent-临时协作)联系；不借用其他员工身份。 |
| 要持续承担项目责任 | 请该项目Coordinator与Rooter沿[现有入职流程](Project-Template/README.md#新项目和工位的创建)登记真实Home和Runtime；本人完成ONBOARD及原生接续。 |

找专业方法从[资源](RESOURCES.md)进入；只为使用现有系统，无需再次初始化、复制Library或创建新员工。

## GitHub 同步

[PAOE 主仓库](https://github.com/xiangscream/PAOE) 是 System 公共源码入口；[Releases](https://github.com/xiangscream/PAOE/releases) 提供固定版本、发布包和校验文件。安装与跨机器升级使用明确 tag，开发改动通过分支和 PR 合入 main，不覆盖已发布 tag。

| 内容 | 同步归属 |
| --- | --- |
| Core、Guide、公共规则、项目母版、Rooter 公共说明 | 本仓库，作为完整 System 一起更新 |
| Workflow、Skill、Tool | [PAOE-Libraries 私有仓库](https://github.com/xiangscream/PAOE-Libraries)，保持原件独立（需要本人权限） |
| 项目业务与成果 | 各独立项目自行维护，按项目安排配置远端 |
| 本机配置、凭据、Contact/Runtime 绑定、消息与工位历史 | 保留本机，不进入 System 公共仓库 |

先保存并提交本机改动，再 fetch 和比较差异；冲突按原件合并，保留人工内容。GitHub 版本已发布与本机已采用分别记录，不能用一次 push 代替运行或 Agent 消费验收。

## 两机经历与协作

个人经历和项目背景沿两机已确认的 Syncthing 内容库共享。各机复制真实项目的 TEAM 页，标明机器、Project、来源与采集时间，方便查同事和职责；具体合作由各机同步维护 Agent 转接，再调用接收端自己的原生提醒。采用与验证见[跨机协作](Guide/guide-cross-machine-experience.md)。

## 新安装

在 Windows、Python 3.10 及以上环境，从 System 根目录执行：

```text
python Core/portable.py plan
python Core/portable.py init --workflow-root <已有Workflow库绝对路径> --skill-root <已有Skill库绝对路径>
python Core/portable.py doctor
python -X utf8 -B Core/code/personal-agent-os/scripts/paos.py --installation-file Core/config/local/installation.json health
```

库须已由其正常工具初始化；System 不复制或改造它们。初始化只创建本机配置和空安装数据，不创建 Project、Home、原生会话或 CAT 服务。已有 Rooter 可显式传 `--rooter-home <现有Home绝对路径>`。

## 旧机器升级

按 [UPGRADE](UPGRADE.md) 采用固定版本，保留本机 Registry、Rooter/项目工位、TODO、消息、绑定、STOP、独立 Libraries 和业务历史。不能直接用公开旧 main 或整包覆盖生产目录。

发布包不含本机实例数据；PROJECTS 是中性入口，目标机器用现有生成器重建自己的页面。已配置、命令可运行和实际 Agent 接续分别验收。

## 版本与复现

`VERSION` 标识 System 版本，`SOURCE.lock.json` 固定 Core 源提交和树。完整 System 是一个 Git 树，Core 是普通文件，不依赖 submodule 或嵌套 Git。

```text
python release.py build --ref system-v0.2.0 --output <输出目录>
python release.py verify <发布ZIP>
```

发布工具从精确 Git 提交读取文件，固定归档顺序、时间和权限；同一 tag 构建两次应得到相同 ZIP SHA-256。
