# 项目库母版

本目录定义**独立 Project Obsidian Vault 的完整基本架构**，目录与文件名可按项目业务适配，但下面各项职责必须有明确落点，且原件唯一（SSOT）。

本页是母版使用说明，不复制进实际项目。新建时使用下面的文件和目录；已有项目继续维护自己的业务原件与工位。

## 标准结构与职责

```text
<Project Vault>/
├── AGENTS.md           # 生效公共运行区 + 项目人工约定
├── INDEX.md            # 最新业务口径与资料/成果导航
├── TEAM.md             # 项目真实成员、职责与专长
├── Inbox/              # 尚未归位的项目输入
├── Materials/          # 原始资料、引用、参考、项目经验
├── Works/              # 正在形成的正文、报告和成果
├── Decisions/          # 正式决策和被接受结论
├── Workstations/
│   └── <home-id>/
│       ├── ENTRY.md    # 流程约束与本人业务入口
│       ├── TODO.md     # Pinned / Current / Tasks / 结果
│       ├── mailbox/    # 持久 Mail 原件
│       ├── notices/    # 输入处理事实
│       │   ├── README.md # 入职与按 Harness 配置唤醒器
│       │   ├── codex.py   # Codex 可执行入口
│       │   ├── opencode.py # OpenCode 可执行入口
│       │   └── wake_entry.py # 共用当前安装与本人工位校验
│       └── Contact     # 如已配置，原生接收/STOP 等入口
└── Archive/            # 退出当前视野但保留追溯的资料
```

`Inbox`、`Materials`、`Works`、`Decisions`、`Workstations`、`Archive` 已是当前 `workstation init` 的标准目录；其他目录、源码库、`.git`、`.obsidian` 及业务文件按实际需要保留。当前业务正文可有多篇，只有各主题的“最新/正式”结论应有唯一权威原件。可选 `HISTORY.md` 仅作完成成果短索引，不复制 TODO 或 Git 历史。

| 母版 | 原件职责 | 已有项目怎样更新 |
| --- | --- | --- |
| [AGENTS](AGENTS.md) | 公共运行区唯一母本；项目约定在公共区外 | 只分发公共区，保留项目约定 |
| [INDEX](INDEX.md) | 项目最新口径、业务原件、仓库及认证取用入口 | 由项目维护；不以母版覆盖业务内容 |
| [TEAM](TEAM.md) | 项目成员职责与专长 | 修改本项目原件后刷新 PROJECTS 聚合 |
| [ENTRY](Workstations/_workstation/ENTRY.md) | 分开说明流程约束与本人业务入口，CLI直接读取 | 生成器只填数据；已有入口按受影响部分合并，重复初始化不覆盖 |
| [TODO](Workstations/_workstation/TODO.md) | TODO v4 的合法样例 | 只校验格式与身份；当前行动由本人维护，不复制样例任务 |
| [入职与唤醒说明](Workstations/_workstation/notices/README.md) | 入职四项要求及 Codex / OpenCode 使用入口 | 创建者须补入 notices 的 README、codex.py、opencode.py、wake_entry.py，并沿 TODO v4 写入 ONBOARD；当前 CLI 不自动带入，已有人工内容不覆盖 |
| [采用公告](../Guide/Templates/project-announcement.md) | 一次真实采用事项的消息样板 | 需要时使用；不作为持续规则或任务状态 |

页面可以互相导航；同一条规则、业务事实和运行定位各有唯一原件。正文只在其归属处维护，导航引用原件，派生区通过现有工具更新。

## 公共区编辑与同步

公共运行正文只编辑 [AGENTS 母本公共区](AGENTS.md)。项目副本携带派生公共区，项目约定保留在标记之外。分发、指纹与人工冲突处理的唯一操作正文见 [公共区统一分发](../Guide/guide-upgrade-adoption.md#公共区统一分发system-agents)。

ENTRY 母本中的 `{{字段名}}` 只替换身份、路径、链接和 CLI 数据，不执行表达式。标准 System 安装自动定位本文件；独立源码需用 `--entry-template` 指明。Core 不另存 ENTRY 文案。字段名称变更应与生成器同步；缺母本、未知字段或缺少必需字段时明确失败，且不创建工位或分配员工号。

项目内导航直接使用相对 Markdown 链接，无需改成变量。身份、安装位置与跨库入口才按需填值。初始化只创建文件，不配置或验证 Harness/Contact；本人随后填写实际状态与恢复方式，不把模板维护说明写进工位正文。

Human 已编辑或确认的正文作为后续修改基线。更新只改当前任务涉及的段落；同步、迁移、升级或接入生成器均不授权重写其余正文。写前重读原件并核对差异；发现并发编辑先合并。备份用于追溯，不能作为覆盖当前原件的理由。

## 新项目和工位的创建

1. Human 明确授权建立独立目录及 Obsidian Vault、登记项目；使用母版建立 AGENTS、INDEX、TEAM，按实际业务填写项目约定；ENTRY 由正常初始化入口读取母本展开，TODO 使用现行写者初始化。不得由示例虚构成员、任务、凭据或业务结论。
2. 先确认 `project register --help` 与当前安装参数，`workstation init` 仅处理已有授权项目和真实 Home；现有 ENTRY/TODO 不被重复初始化覆盖。
3. 完整填写项目根和本人真实安装入口。示例命令（参数核当前同版 `--help`）：

```powershell
python -X utf8 -B Core/code/personal-agent-os/scripts/paos.py --installation-file Core/config/local/installation.json --library-roots-config Core/config/local/library-roots.json workstation init '<project-id>' '<home-id>' --root '<项目根绝对路径>' --objective '<本人目标>' --guide-root Guide
```

4. 将本母版的 `notices/README.md`、`codex.py`、`opencode.py`、`wake_entry.py` 带入新工位，在本人 TODO 合并 `ONBOARD` 入职任务：了解 PAOE、继承业务理解、更新 TEAM、按实际 Harness 配置并验证唤醒器。当前 CLI 初始化不会自动复制这些文件或导入母版任务，创建者须补齐这一步；已有 ENTRY/TODO/说明和脚本保留人工编辑，已完成入职不重置。任务由本人沿 TODO v4 写入入口维护，不用母版整份覆盖。
5. 从实际 Home 打开生效 AGENTS/INDEX/ENTRY/TODO 与必要业务原件，验证 Guide、Library、Tool 定位，检查旧工作循环路径已退出；已有项目普通文件只在批准范围内修改。TEAM/ENTRY 改动后运行 System 的 `PROJECTS --check`，不手改派生成员表。

通用行为写入 AGENTS 公共母本；专题操作在 [Guide](../Guide/README.md)，专业方法在独立 Libraries。代码仓库自身的 AGENTS 保持独立的工程约定，不被项目公共区同步器覆盖。

## 修改后检查

修改规则或母版时，交付范围包含受影响的引用方、生成器和实际入口。先用旧路径、命令、字段查使用方，完成对应修改，再从 System 根执行一次只读检查：

```powershell
python -X utf8 -B .\Core\code\personal-agent-os\scripts\paos_template_check.py --system-root . --installation-file .\Core\config\local\installation.json --retired-locator 'Protocols/' --retired-locator 'wf-agent-work-cycle.md'
```

检查包括：母版实际展开、TODO v4、现行本地 Markdown 链接与锚点、指定退役路径、已登记项目的公共区和 PROJECTS 是否过期。它不改真实文件、不新建 Project、不唤醒 Runtime。可追加 `--changed '<已修改文件>'` 列出检查范围内指向该文件的直接链接；独立母版预检可用 `--templates-only`，不能代替本机完整检查。

检查器不验证 notices 文件已复制、ONBOARD 已写入或 Harness 已绑定；这些须在实际创建后按入职任务核对。

- AGENTS 公共区过期：沿上方分发入口更新，保留人工内容。
- PROJECTS 过期：沿聚合页已有入口重建，再检查。
- 其他问题：回原件处理；链接能打开仍需核对相关文字、命令含义和责任是否一致。

一次修改按“原件 → 使用方 → 检查 → 实际入口回读”收口。格式或路径检查通过，不等于外部网页、原生唤醒或业务语义已验证。不要后台监控、全库重写或给每页另建依赖台账。
