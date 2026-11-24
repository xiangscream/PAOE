# 项目库母版与标准结构

本目录定义 **独立 Project Obsidian Vault 的标准架构与母本规范**。各目录与文件职责有明确落点，且保持单点权威（SSOT）。

本页是母版设计与创建说明，不复制进实际业务项目。

---

## 1. 标准结构与文件职责

```text
<Project Vault>/
├── AGENTS.md           # 生效公共运行区（底座契约） + 本项目特殊约定
├── WORK-LEAD.md        # 仅临时负责人载入的组织与述职指南
├── INDEX.md            # 项目最新业务口径、成果导航与外部原件稳定链接
├── TEAM.md             # 项目在队成员、职责、专长、Harness 与工位入口
├── HISTORY.md          # 按业务主题归并的阶段成果与关键经验
├── Inbox/              # 尚未归位的临时输入与待确认材料
├── Materials/          # 原始参考资料、外部输入快照与项目经验（TIPS.md）
├── Works/              # 正在形成的正文、过程稿、评议与交付物
├── Decisions/          # 正式决策、被接受结论与阶段基线
├── Workstations/
│   └── <Sxxx>/
│       ├── ENTRY.md    # 工位运行入口、环境恢复与职责导航
│       ├── TODO.md     # 唯一生效行动状态机（Pinned / Current / Tasks）
│       ├── mailbox/    # 接收的 Durable Mail 原件
│       ├── notices/    # 输入处理记录与唤醒器脚本（README / codex / opencode / dsh / wake_entry）
│       └── Contact     # 本人工位公开联系包（按 OPS 生成）
└── Archive/            # 库内历史简短导航；大批历史正文置于库外
```

### 母本职责对照表（SSOT）

| 母版 / 文件 | 原件职责 | 维护与更新方式 |
| --- | --- | --- |
| [AGENTS](AGENTS.md) | 公共运行区唯一母本；项目特殊约定留在公共区外 | 统一分发公共区；保留项目原有特殊约定 |
| [WORK-LEAD](WORK-LEAD.md) | 临时负责人对齐、组织和收尾的方法 | 同一公共区分发；在负责 Task 中关联或显式 context read，普通成员不默认载入 |
| [INDEX](INDEX.md) | 项目最新业务口径、业务原件与外部权威链接 | 由项目合成人维护；不以母版覆盖业务内容 |
| [TEAM](TEAM.md) | 项目成员职责、专长、Harness 与工位索引 | 按真实分工维护，修改后刷新 PROJECTS 聚合 |
| [HISTORY](HISTORY.md) | 按业务主题汇总的阶段成果、关键判断与经验 | 由合成人从成员已完成 TODO 和成果归并 |
| [ENTRY](Workstations/_workstation/ENTRY.md) | 工位环境恢复命令与本人工位导航 | `workstation init` 初始化展开，后续保留人工配置 |
| [TODO](Workstations/_workstation/TODO.md) | TODO v4 结构规范与样例 | 本人维护；`todo-update` 维 Current，`todo-write` 维 Tasks |
| [入职与唤醒说明](Workstations/_workstation/notices/README.md) | 入职四项要求及各 Harness 唤醒配置 | 新工位创建后由创建者带入，保留人工编辑 |

---

## 2. 规则维护与公共区分发

1. **公共运行区**：只编辑 `System/Project-Template/AGENTS.md` 中的公共区。各项目副本承载派生区，项目独立约定保留在标记之外。具体分发操作见 [公共区统一分发](../Guide/guide-upgrade-adoption.md#公共区统一分发system-agents)。
2. **ENTRY 模板展开**：ENTRY 母本中的 `{{字段名}}` 由初始化工具替换身份与路径；不执行复杂表达式。Core 不另存文案。
3. **保护人工基线**：Human 已编辑或确认的正文为后续修改基线。更新只改当前任务涉及段落，不擅自重写整份文件。

---

## 新项目和工位的创建

1. **建立 Vault**：Human 明确授权建立目录与 Obsidian 库，使用母版初始化 AGENTS、WORK-LEAD、INDEX、TEAM、HISTORY。
2. **登记项目与成员**：
   - 为新成员选定全局未使用的员工号（如 S070）。
   - 新项目执行 `paos project register`，加入已有项目执行 `paos project home-add`。
3. **初始化工位**：
   使用已登记的机器入口执行 `workstation init`：
   ```powershell
   paos workstation init '<project-id>' '<本人Sxxx>' --root '<项目根绝对路径>' --objective '<本人目标>'
   ```
4. **补齐入职套件**：
   将 `notices/` 目录（`README.md`、`codex.py`、`opencode.py`、`dsh.py`、`wake_entry.py`）复制进新工位，并在本人 TODO 合并 `ONBOARD` 任务。
5. **入职验证**：
   本人从原会话执行 ENTRY 中的恢复命令，核验方法与工具入口，完成首封 Mail 验收后回告。

---

## 修改后检查

修改公共母版或关联规则后，交付前执行一致性检查：

```powershell
python -X utf8 -B .\Core\code\personal-agent-os\scripts\paos_template_check.py --system-root . --installation-file .\Core\config\local\installation.json
```

- 检查范围包括：母版实际展开有效性、TODO v4 结构、本地 Markdown 链接有效性、项目公共区是否过期。
- 一次修改按“**原件修改 → 使用方联动 → 模板检查 → 实际入口回读**”完整闭环。
