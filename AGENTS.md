# PAOS Portable / PAOE 开发入口

本仓库保存代码与随包方法资产；本机项目、工位和当前登记的方法库不一定在本仓库内。

- 修改代码前读 [代码边界](code/personal-agent-os/AGENTS.md) 与 [开发准则](code/personal-agent-os/docs/DEVELOPMENT-PRINCIPLES.md)。
- 共享工作规则的唯一正文是 [Agent 工作循环](libraries/workflow/Workflows/wf-agent-work-cycle.md)；[工作入口](libraries/workflow/Guides/guide-work-method.md) 与 [操作入口](libraries/workflow/Guides/ops-entry.md) 只做导航。已安装 Agent 从本人 ENTRY 进入其实际登记的库，不把随包副本当作已经采用的正文。
- ENTRY 只生成身份、安装定位和源文件入口。TODO v4、项目正文、Mail/Notice、Contact 各沿现有职责维护；不复制规则或新增任务状态库。
- 只修改当前任务范围内的代码与方法资产。候选测试不得改真实工位、凭据或生产 Runtime；重复初始化不得覆盖已有 ENTRY/TODO。

在仓库根验证：

```sh
python code/personal-agent-os/scripts/verify.py
node --test tests/board-ui.test.mjs
```

代码与文档检查通过不代表真实 Agent 已读取新版指南或完成原生接续；采用时用当前安装的实际入口核验。
