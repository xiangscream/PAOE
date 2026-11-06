# 资源

<!-- paoe:human-intro:start -->
> 先按任务选 Workflow、Skill 或 Tool，再打开独立 Libraries 中的原件。
<!-- paoe:human-intro:end -->

<!-- paoe:agent-reference -->
## 操作与参考

## 专业方法与工具

| 类型 | 用来做什么 | 原件入口 |
| --- | --- | --- |
| Workflow | 一类任务的步骤、配合与交付方法。 | 登记的 `workflow_root/CATALOG.md` |
| Skill | 专业判断与具体操作，例如写文档、研究、制作图表。 | 登记的 `skill_root/CATALOG.md` |
| Tool | 工具能力、使用入口和调用要求。 | 登记的 `tool_catalog` |

实际根由本机 `library-roots.json` 登记。Guide 中的 `<workflow_root>`、`<skill_root>` 指该登记根；用下方检索命令取得当前可读的 `source_path`。Catalog 是派生目录，正文仍在命中的源文件。

## 按当前任务找原件

```powershell
& "$env:USERPROFILE\.paos\bin\paos.cmd" library search '写作'
```

这是标准Windows已安装入口，其他部署沿[当前安装入口](README.md#已安装机器上的首次使用)。它读取本机已登记的库配置，无需从同事工位借路径，也不需要手加包内的`--library-roots-config`。

将“写作”换成本次任务关键词，打开命中的`source_path`后使用。检索为字面关键词匹配，多个词用空格分隔；零匹配时可换具体关键词或看Library用途表，不能据此认定没有方法。`library_roots_not_registered`则是安装或库配置问题，先用同一入口的`library roots show`核实，不重新安装一套库。

System的启动、接入和通信规则在下方System Guide；这里的检索只查已登记的Workflow与Skill。方法的使用与改进沿Workflow库README的“方法使用与改进”，源文件是唯一正文。工具的具体权限和调用按本机Tool Catalog核对。

## System 的共同规则

[Agent 公共运行母本](Project-Template/AGENTS.md) · [System Guide](Guide/README.md) · [项目库母版](Project-Template/README.md)

通用规则和专业方法分别在各自原件维护。
