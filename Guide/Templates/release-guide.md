---
schema: paos-workflow/v1
id: template-release-guide
title: 发布说明模板
description: 固定发布版本、影响范围、采用入口、验证与回退。
tags: template, release, adoption
status: active
version: 6
---

# <版本/变更> · 发布说明

## 版本与范围

| 项目 | 本次准确值或原件 |
| --- | --- |
| 状态 | <候选/已接受/已安装；按事实填写> |
| Source | <已审候选 SHA、合并 SHA、实际采用 SHA；未发生则注明> |
| Guide / Libraries | <受影响原件、版本或提交；分别登记，不以 Source SHA 代替> |
| 当前安装 | <installation-file 绝对路径、实际 source_root 与 CLI> |
| 方法库配置 | <library-roots-config 绝对路径与实际库根> |
| 影响范围 | <实际项目/Home 与组件；不预填项目编号，不默认全员升级> |

## 变化与采用

<使用者会看到什么变化、需要做什么；必要时直链对应原件，不复制完整操作手册。>

1. 按 [发布采用](../guide-upgrade-adoption.md) 确定切换范围和恢复点；仅重载受影响组件。
2. 从本人固定 ENTRY 定位，按项目生效 AGENTS 的恢复要求读全必要原件，再接续原责任。只更新确有变化的入口与行动，保留人工编辑。
3. 保留健康会话、模型和 STOP；真实需要换 Runtime 时按 [接班指南](../guide-runtime-handoff.md) 办理。不为文件操作恢复旧 Core HTTP、Dashboard 或未配置的 CAT。
4. 有实际工作时观察真实接续；没有样本则记待观察，保留暂停、人工或离线例外，不制造签收任务。

## 操作入口与验证

发布人用当前版本 `--help` 核对命令，将 `<当前 CLI>` 换成可直接执行的命令前缀，显式固定本次安装与方法库配置；Windows/WSL 分别使用实际可达路径。

```text
<当前 CLI> health
<当前 CLI> install show
```

<仅补本次变化需要的命令、目标参数与实际验证结果；记录版本、覆盖范围、跳过项和剩余断点。>

代码合并、安装采用、Mail 保存、原生提醒受理、Agent 消费与业务接受分别说明。未执行的检查写未验证；未变化范围可引用同版已接受证据，不为每次文案修订重跑无关 Runtime。

## 反馈与回退

- 项目内容与责任：<对应 Coordinator 的正式联系入口>。
- 安装与运行：<安装级 Rooter 的正式联系入口>。
- 未完成项：<具体问题、影响范围、接续人和解除条件；没有则注明>。
- 回退：<本次对应的数据/代码/入口恢复点、必要动作与新增业务的保留方式>。

采用汇总按需使用 [采用结果](adoption-result.md)；同一事实引用原件，不另造进度或审批账本。
