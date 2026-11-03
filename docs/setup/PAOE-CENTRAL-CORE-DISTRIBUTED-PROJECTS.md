# PAOE 本机配置方向：Centralized Core + Decentralized Projects

> 状态：已确认的目标架构与分阶段配置指导  
> 适用对象：PAOE 本机主要实施端（Rooter）与架构复核端  
> 基线：Portable 本机采用版本 7cd530029db1c95cf4dd01bb0b9e8a9df2421f31；远端架构/学习文档基线 b8d6263e4da7b045c48a6bb2acbd4230d83c653a  
> 本文性质：配置方案与边界合同，不是本机实际配置状态报告。路径和对象状态必须在实施时重新核验。

## 1. 架构决策

采用 **Centralized Core + Decentralized Projects（集中 PAOE 主体，分散 Project）**。

- PAOE 的代码、Installation、共享 Library、Rooter 和 System Vault 作为一个相对集中的主体，便于维护、理解、版本控制和 SSOT。
- 每个 Project 保留独立业务目录和自己的事实边界；Project 可以位于不同磁盘或存储设备。
- PAOE 通过 Project Registry 中的绝对 root_path 定位 Project，不把项目正文搬入中央目录，也不要求各项目位于同一个 Obsidian Vault。
- System Vault 是 Human-readable 的系统说明、导航和操作入口，不是第二份 Project Registry、TODO、Library Catalog 或项目知识库。
- Obsidian 是主要的人类阅读和编辑界面；文件系统是透明的物理基础；CLI 是受约束的自动化操作入口；Board 是可选的可视化面板。

**本轮实施重点：建立中央 System Vault，并连接当前真实资源。不得以此为由迁移现有 Project。**

## 2. 目标物理布局

### 2.1 中央 PAOE 主体

建议将以下资产集中在主要工作电脑的稳定存储位置（当前盘符与路径以 S0 复核为准）：

| 资产 | 目标位置/形态 | 权威职责 |
|---|---|---|
| Portable Repository | 当前 PAOS-Portable 仓库 | Python Core、CLI、Frontend、Tests、随包示例；代码以 Git 为准 |
| Installation | Portable 的本机 config/local 与安装数据根 | 当前机器的 source_root、data_root、Library roots 等定位配置 |
| Project Registry | Installation 的 data_root 下 | Project ID、绝对 root_path、Home 名册、Coordinator 定位 |
| Rooter Home | 中央安装级 Home | 安装与系统维护；不伪装成 Project 成员 |
| Shared Workflow Library | 独立共享目录 | Workflow、Guides、Templates 的唯一正文及派生 Catalog |
| Shared Skill Library | 独立共享目录 | Skill 正文及派生 Catalog |
| Tool Catalog | 独立共享目录中的目录文件或现有登记形态 | 工具说明、入口和已核实的可用性记录 |
| PAOE System Vault | 新建的独立 Obsidian Vault | 人类可读的系统架构、路径解释、资源导航、运行手册和学习入口 |

System Vault 应与 Portable 源码仓库、Shared Libraries、Project Vaults 分开。推荐在中央工作盘选一个稳定位置，例如 C:\Users\ASUS\Documents\PAOE-System；该路径只是候选，创建前必须核实不存在同名用户资料、目标盘可用和 Obsidian Vault 状态。不得将 System Vault 建在 Portable 仓库内部，也不得把共享库复制进去。

### 2.2 分散 Project

Project Vault 是独立业务资产，允许分布在 D、E、其他本地盘或未来挂载的存储设备。示意：

~~~text
D:\Projects\Project-A\       # 一个独立 Project Vault
E:\Projects\Project-B\       # 另一个独立 Project Vault
F:\Projects\Project-C\       # 另一个独立 Project Vault
~~~

上面是目标形态示意，不是现有目录或迁移指令。

PAOE 主体不随 Project 复制。各 Project 的 Registry 记录各自绝对 root_path，其业务材料、INDEX、TEAM、Works、Workstations 和 Git 历史留在项目自己的边界内。

## 3. 各类 Obsidian Vault 的职责

### 3.1 PAOE System Vault（中央系统说明库）

**职责：解释整个 PAOE 如何组成，以及如何找到各个权威原件。**

建议目录：

~~~text
PAOE-System/
├── HOME.md
├── Architecture/
│   ├── SYSTEM-MAP.md
│   ├── DATA-OWNERSHIP.md
│   ├── MODULE-MAP.md
│   └── DATA-FLOW.md
├── Installation/
│   ├── CURRENT-MACHINE.md
│   ├── PORTABLE.md
│   ├── PATHS.md
│   └── DEPENDENCIES.md
├── Libraries/
│   ├── WORKFLOW.md
│   ├── SKILL.md
│   └── TOOL.md
├── Projects/
│   └── PROJECT-INDEX.md
├── Agents/
│   ├── AGENT-DIRECTORY.md
│   └── ROOTER.md
├── Runtime/
│   ├── CODEX.md
│   ├── OPENCODE.md
│   ├── CONTACT.md
│   └── CAT.md
├── Frontend/
│   └── BOARD.md
├── Operations/
│   ├── DAILY-USE.md
│   ├── RECOVERY.md
│   └── BACKUP.md
└── Learning/
    ├── ROADMAP.md
    └── NOTES/
~~~

目录可按实际盘点微调，不为凑齐目录创建空文档。

System Vault 可编辑的内容：架构解释、操作手册、学习笔记、资源用途说明、已验证的维护流程。

System Vault 不拥有的内容：Project 正文、Agent TODO、Mail/Notice 状态、Workflow/Skill 正文、Installation 权威配置、Project Registry。

### 3.2 Shared Workflow Library

独立目录、独立登记。Workflow、Guide、Template 的源文件由对应维护流程更新；CATALOG.md 是派生导航，不手工维护为第二份事实。

System Vault 的 Libraries/WORKFLOW.md 只说明：
- 当前实际登记根目录；
- Guides / Workflows / Templates 的职责；
- 关键入口文件及用途；
- 如何打开源文件；
- 如何通过 CLI 搜索；
- Catalog 的派生属性。

不得复制 wf-agent-work-cycle 或具体 Guide 正文。

### 3.3 Shared Skill Library

继续使用 Installation 实际登记的独立 Skill 根。System Vault 只提供分类、代表性 Skill、搜索方式和源文件定位。Skill 正文的唯一原件仍留在 Skill Library。

### 3.4 Tool Catalog

如果当前工具目录只是一个 Markdown Catalog，不需要为了视觉整齐把它改造成独立 Obsidian Vault。

必须区分四种状态：
1. Catalog 有说明；
2. 本机存在安装文件或命令；
3. 某个 Runtime 已配置并授权；
4. 在当前 Runtime 中实际调用验证成功。

System Vault 不得把第一种状态写成第四种。可用性记录应标注 Runtime / 平台、检查时间和证据；不确定时写 unverified。

### 3.5 Project Vault

Project Vault 保存项目自己的：
- INDEX.md、TEAM.md 或该项目当前采用的成员/入口原件；
- Materials、Works、决策、需求、PRD、会议资料和归档；
- 属于项目的 Workstations / Agent Homes；
- 项目自身的版本历史。

System Vault 的 Project 页面只记录 Project ID、Registry 中的定位、Vault 名称、访问状态和入口链接，不复制业务摘要、任务或成果正文。

### 3.6 Agent Home 与 Rooter

Project Agent Home 继续属于其 Project Vault；其 ENTRY.md、TODO.md、mailbox、notices 和 Contact 沿现有合同维护。

Rooter 是安装级 Home，属于中央 PAOE 主体，不属于任何 Project。System Vault 单独说明 Rooter 的职责、Home 定位和维护入口；不创建虚构 Project，也不复制 Rooter TODO。

## 4. SSOT 与可编辑性边界

| 资产 | 唯一事实源 | 人工编辑规则 | System Vault 表达 |
|---|---|---|---|
| PAOE 代码 | Portable Git 仓库 | 通过 Git 分支/PR 修改 | 代码地图、仓库链接 |
| Installation | 当前 installation.json 与登记配置 | 可读；修改前核对 schema、路径和影响，优先用安装工具 | 解释字段；可生成带时间戳快照 |
| Project Registry | data_root/project-registry/projects/<id>.json | 可读；谨慎修改，优先用 CLI | 由 Registry 生成项目目录快照 |
| Project 业务内容 | 各 Project Vault 原件 | Human / Agent 按项目约定编辑 | 路径与入口链接 |
| Workflow / Guide / Template | Shared Workflow Library 源文件 | 按维护流程编辑源文件 | 资源索引，不复制正文 |
| Skill | Shared Skill Library 源文件 | 按 Skill 维护流程编辑 | 资源索引，不复制正文 |
| Tool Catalog | 当前登记的 Catalog 源文件 | 可以维护说明；可用性必须有证据 | 用途与验证状态 |
| Agent TODO | 对应 Home 的 TODO.md，当前合同 paos-todo/v4 | 可阅读；结构化区域遵循现有写入合同 | 只链接，不汇总复制 |
| Mail | Home mailbox 中的消息原件 | 原则上不直接改投递原件 | 说明读取入口，不复制正文 |
| Notice | Home notices 中的输入处理事实 | 状态沿现有 CLI / writer 维护 | 说明语义，不复制状态 |
| Board 视图 | 由 Registry、Vault、Home、Library 等原件派生 | 不作为业务事实写者 | 说明数据来源与边界 |

### 4.1 快照与实时事实

CURRENT-MACHINE.md、PROJECT-INDEX.md、AGENT-DIRECTORY.md 可以由只读检查结果生成或刷新，但必须：
- 标注生成时间；
- 标注读取来源；
- 说明是快照而非权威原件；
- 不把缺盘或读取失败解释成项目不存在；
- 不自动删除 Registry 记录或创建替代项目。

不建立第二份可独立编辑的路径配置。

## 5. 中央核心与多盘 Project 的解耦规则

1. Project Registry 使用绝对 root_path 定位每个 Project；不同 Project 可以位于不同盘符。
2. root_path 指向 Project 自己的 Vault 根目录，不指向共同的总 Obsidian Vault 根目录。
3. 某个盘符暂时不可访问时，状态应为 Unavailable / Unverified，保留 Registry 原记录；禁止自动重建、改写路径或注销项目。
4. 路径存在不等于 Vault 内容健康；路径检查、Obsidian 可打开、Git 状态和 Agent Home 检查是不同验证。
5. Portable、Installation、Rooter 和 Shared Libraries 不随 Project 移动。
6. Project 移动属于显式迁移：先复制候选、核对文件数与哈希、核对 Vault / Git / Obsidian 配置和引用，再更新 Registry；确认新位置可用后才考虑清理旧副本。不得直接剪切。
7. 不使用 symlink、junction 或盘符映射作为默认解耦机制；只有明确的跨平台需求和可验证恢复方案出现时再评估。

### 5.1 每个 Project 独立 Obsidian Vault / Git：必要性区分

**本轮不是必需项。**

本轮只建立 System Vault，并把现有 Project 作为独立导航目标接入。当前项目即使仍位于同一个 D 盘 Obsidian Vault / Git 根目录，也可以继续正常使用；不得为了 System Vault 先拆分现有项目。

**后续目标与建议：**

- **独立 Obsidian Vault：** 对需要跨盘存储、独立打开、独立备份和独立迁移的 Project，推荐一个 Project 对应一个 Vault。新建此类 Project 时优先采用该布局；现有 Project 逐个评估，不批量迁移。
- **独立 Git 仓库：** 对需要独立版本历史、独立备份/协作和独立迁移的 Project，推荐 Git 根目录与 Project Vault 根目录一致。它是按项目需要采用的目标，不要求每个轻量 Project 都必须使用 Git。
- **现有共享 D 盘 Vault / Git：** 作为当前事实保留。拆分前必须单项目试点，验证 Obsidian 链接、Git 历史、忽略规则、附件、Agent Home 和 Registry 路径；确认收益后再决定是否逐个迁移。
- **多盘 Registry 定位：** 在未来拆分前即可通过隔离 fixture 验证；这不等于现在要修改生产 Registry。

## 6. Obsidian 的呈现方式

- PAOE System Vault 是 Human 的默认总入口；从 HOME.md 能进入架构、Installation、Library、Projects、Agents、Runtime、Frontend、Operations 和 Learning。
- Workflow / Skill / Project Vault 仍保持独立；System Vault 用文件系统链接或经验证的 Obsidian URI 打开其原件。
- 不假设 Obsidian URI 一定可用。先验证 Vault 名称、文件路径和实际打开结果；验证失败时保留准确绝对路径和手动打开说明。
- 不把外部 Vault 文件复制到 System Vault 以换取“内部链接”。
- 不要求安装 Dataview、Templater 或其他社区插件。原生 Markdown 链接和可读表格优先；确有收益再单独评估插件。
- 可生成的索引页面必须标注来源与生成时间。人工维护的说明页与机器生成的快照分开。

## 7. 前端 Board 的角色

现有 PAOE Board 保留为**可选关系与状态浏览面板**，不升级成第二个系统控制台。

- 展示 Project / Agent 关系、Home 详情、TODO 读面、近期 Mail 摘要、项目口径和可选 CAT 房间。
- 具体数据来自 Registry、Project Vault、Agent Home、Shared Library 和外部 CAT。
- 少量动作可调用既有 CLI / CAT；发生写入的按钮必须明确说明副作用。
- 节点位置和连线是视图状态，不是持久组织关系或任务依赖。
- Board 不负责编辑 Project 正文、Workflow/Skill 正文、Installation 权威配置或 TODO 结构化状态。
- 关闭 Board 不影响 Obsidian、CLI 和本地文件工作。
- 不为了展示中央/分布式布局而立即重做前端；System Vault 是 Human 的主入口，Board 是辅助视图。

## 8. 分阶段实施

### S0 — 现况复核（只读）

重新核对当前真实状态，不能直接沿用旧报告中的路径和数量：
- Portable 本机 branch / HEAD / dirty 状态，与远端 main 的差异；
- Installation 的 source_root、data_root、library_roots_config、rooter_home；
- Workflow / Skill / Tool 的实际登记根和存在性；
- 当前 Registry 中的全部 Project ID、绝对路径和可访问状态；
- 每个 Project 的 Obsidian Vault 名称、物理根目录、Git 根目录；
- 每个已登记 Home 与 Rooter 的 ENTRY / TODO 存在性；
- Obsidian 当前已打开 Vault、Vault 配置和是否已有同名 System Vault；
- 现有 47 项 D 盘 Git 工作区状态等历史报告中的敏感/易变化事项，实施前重新检查，不假定仍然相同。

S0 不创建、移动、删除或修改任何文件。

### S1 — 建立 PAOE System Vault（只新增）

- 先确认目标目录不存在或确认它就是用户明确指定的空 Vault；不得覆盖同名目录。
- 在中央工作盘创建独立 Obsidian Vault 和最小目录结构。
- 建立 HOME.md、架构图、数据归属、路径解释、Library / Project / Agent 导航和学习入口。
- 机器配置页面记录来源和读取时间；不另造可写路径配置。
- 不修改 Portable、Installation、Registry、Library 或任何 Project。

### S2 — 连接真实资源（只新增导航）

- 将实际 Workflow / Skill / Tool 根、当前 Project Vault、Home 和 Rooter 接入 System Vault。
- 每个链接记录资源类型、权威路径、维护者/写者、可访问性和验证方式。
- Obsidian URI 必须实际打开验证；否则提供路径与手动打开方式。
- 不复制正文，不批量重建 Catalog，不发送 Mail / Notice，不触发 Wake。

### S3 — 定点修复断链

只有在 S0 确认目标文件存在且引用确实失效后，才修复旧绝对路径、过期链接或入口文案。先改一份候选并核对引用，不进行全库机械替换。
TEAM 缺失时先判断该项目采用的真实成员原件（如 Agent身份登记.md、PAOS-ENTRY.md）；不能为了满足 CLI 固定读取 TEAM.md 而虚构职责。需要新增/转换名册时另列方案，不在本阶段代造角色事实。

### S4 — 多盘能力验证（隔离环境）

- 使用临时目录/测试 fixture 模拟两个不同盘符或挂载根下的 Project Registry 记录。
- 验证 CLI 可以分别定位、读取两个 Project。
- 模拟其中一个盘不可访问，确认记录被保留且不会自动创建项目或覆盖路径。
- 不改生产 Registry，不迁移 D 盘现有项目。

### S5 — 单项目独立 Vault / Git 试点（后续可选）

只有在真实项目需要独立存储/迁移，且 Human 选择低风险对象后才开始：
- 选一个项目做 staged copy；
- 核对内容、附件、Obsidian 配置、Git 历史、链接、Workstations 和 Registry；
- 新旧目录并存，验证新位置；
- 经明确采用后再更新 Registry；
- 旧目录清理必须另行确认，不能与 cutover 合并。

不得将 S5 作为建立 System Vault 的前置条件。

## 9. 轻量 Gate 与验收

### Gate A — 资源定位正确

- System Vault 指向当前真实登记的 Portable、Library、Project 和 Home。
- 不存在把随包 Library 误认成实际共享库的情况。
- 缺盘、未登记和未验证状态被明确区分。
- 无秘密、凭据或私有 Mail/Notice 正文泄漏。

### Gate B — SSOT 与链接边界正确

- System Vault 只保存解释、导航和有来源标注的快照。
- Workflow / Skill / Project 正文没有被复制。
- Installation / Registry 没有出现第二份可写配置。
- 所有声称“可打开”的 Obsidian URI / 文件链接至少实际验证一次；未验证的明确标注。

### Gate C — Human 可理解

Human 从 System Vault 的 HOME.md 出发，能够找到：
1. Portable 代码和 CLI；
2. 当前实际 Workflow / Skill / Tool；
3. 每个已登记 Project Vault；
4. Project 内 Agent Home 和 Rooter 的入口说明；
5. Installation、Runtime、Board 和操作指南。

一次实际 Obsidian 打开与导航演示即可，不设使用次数或 Agent 行为成功率。

### Gate D — 不破坏现有系统

- 本轮没有迁移或重命名现有 Project；
- 没有重写成员 TODO、Mail、Notice、Contact；
- 没有触发 Runtime Wake 或 CAT 写操作；
- 没有覆盖旧 Vault、Library 或 Git 工作区；
- 既有 CLI / Portable 验证不因新增 System Vault 受影响。

## 10. 本轮范围与后续范围

### 本轮必须完成

1. 复核本机真实路径与 Obsidian 状态（S0）。
2. 在中央工作盘建立独立 PAOE System Vault（S1）。
3. 将现有真实 Shared Libraries、Project Vaults、Agent Homes、Rooter、Portable 和前端入口接入导航（S2）。
4. 对实际确认的关键失效链接做最小修复候选（S3；若涉及既有权威文件写入，先留候选和差异供复核）。
5. 使用隔离 fixture 验证多盘绝对路径定位与缺盘保留规则（S4）。

### 本轮明确不要求

- 不移动现有 8 个 Project；
- 不拆分当前 D 盘共享 Obsidian Vault；
- 不拆分当前 D 盘 Git 仓库；
- 不重建 Agent Home 或修改成员 TODO；
- 不迁移/复制 Shared Library；
- 不重写 PAOE 前端；
- 不改 Project Registry schema、Installation schema 或 TODO v4；
- 不把每个 Project 独立 Git 作为强制条件。

### 后续目标

- 新项目优先采用独立 Project Vault，允许按盘分布；
- 需要独立版本历史的项目采用独立 Git 根；
- 现有项目按需逐个评估是否拆分；
- 通过 Registry 的绝对路径统一发现，不通过复制/同步项目正文实现统一视图。

## 11. 实施回报格式

本机主要实施端每阶段回报：
- 实际路径和 Git/Obsidian 状态；
- 新建或修改文件清单；
- 资源导航目标及打开验证证据；
- 未解决的链接/配置断点；
- 是否触碰既有权威原件；
- Gate 结果与下一步。

路径与状态以实施当时的本机读取为准。本文中的旧报告路径只作为调查线索，不作为可直接执行的命令或迁移目标。
