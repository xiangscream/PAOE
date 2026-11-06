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
python -X utf8 -B Core/code/personal-agent-os/scripts/paos.py --installation-file Core/config/local/installation.json --library-roots-config Core/config/local/library-roots.json library search '任务关键词'
```

打开结果的 `source_path` 再使用。工具文档、本机安装、当前 Runtime 的权限和实测调用是不同事实，按当前任务核对需要的能力。

命令在 System 根目录执行；已有机器使用自己的权威安装与库配置，不导入另一台电脑的库路径。

## System 的共同规则

[Agent 公共运行母本](Project-Template/AGENTS.md) · [System Guide](Guide/README.md) · [项目库母版](Project-Template/README.md)

通用规则和专业方法分别在各自原件维护。
