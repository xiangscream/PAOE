---
schema: paos-workflow/v1
id: template-workstation-entry
title: Workstation ENTRY 模板
description: 只保存身份、安装与权威原件入口；通用行为链接工作循环，方法与操作按需查找。
tags: template, workstation, entry
status: active
version: 10
---

# ENTRY 正文模板

生成器与人工维护都只填写当前安装的真实定位，不把占位符原样写进工位。具体工作行为以共享 [Agent 工作循环](../Workflows/wf-agent-work-cycle.md) 为准；本页是入口结构参考，不另写恢复步骤、TODO 规则或通信协议。

```markdown
# Agent Workstation — <完整HomeID>

## 身份

- Project：<project-id>
- Agent：<完整HomeID>
- 工位：<absolute-workstation-root>

## 当前工作与项目

- 当前行动：[TODO](TODO.md)
- 当前项目入口：[INDEX](<absolute-project-root>/INDEX.md)
- 本人规则：[AGENTS](<role-rules-path>)
- 项目规则：[Project AGENTS](<absolute-project-root>/AGENTS.md)
- 同事与职责：[TEAM](<absolute-project-root>/TEAM.md)
- 持久输入：mailbox/、notices/

## 安装与共享入口

- 安装描述：<当前 installation.json 的绝对路径>
- 方法库配置：<本次初始化实际选定的 Library roots config 绝对路径>
- CLI：<当前解释器、Source CLI、显式 installation-file 与 library-roots-config 组成的可执行命令>
- 通用工作正文：[Agent 工作循环](<workflow-root>/Workflows/wf-agent-work-cycle.md)
- 恢复入口：[恢复](<workflow-root>/Workflows/wf-agent-work-cycle.md#恢复)
- 按任务找方法：[GUIDE](<workflow-root>/Guides/guide-work-method.md)
- 按目的找操作：[OPS](<workflow-root>/Guides/ops-entry.md)
- Workflow 目录：<workflow-root>/CATALOG.md
- Skill 目录：<skill-root>/CATALOG.md
- Tool 目录：<当前登记的 tool_catalog，未登记则明确标注>
```

Project 的 INDEX、TEAM、角色规则缺失时如实标注，不为入口齐全生成业务正文。共享库沿实际登记定位，不假定 Workflow、Skill 与 Tool 相邻。Rooter 使用安装级 Home 入口，不填写虚假的 Project。

新工位使用当前生成器；已有 ENTRY/TODO 的人工内容不因重复初始化被覆盖。采用新版入口时，在当前工位人工对齐必要链接即可，不批量重建工位。入口变更不代表 Agent 已读正文或原生提醒已验收。
