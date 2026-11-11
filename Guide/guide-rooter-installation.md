---
schema: paos-workflow/v1
id: guide-rooter-installation
title: Rooter 安装与运行维护
description: 按需读取：安装定位、原会话恢复、服务可达与成员运行例外。
tags: rooter, installation, recovery
status: active
version: 18
---

# Rooter 安装与运行维护

<!-- paoe:human-intro:start -->
> [!info] 给使用者
> 这是系统维护者的工作说明。程序安装、共享库位置和成员运行入口出问题时，Rooter 按这份指南定位和处理。
>
> **从这里开始：** 按下面的适用范围和步骤使用；需要执行时让 Agent 从“操作与参考”继续。
<!-- paoe:human-intro:end -->

<!-- paoe:agent-reference -->
## 操作与参考
<!-- paoe:reading-header:end -->

Rooter沿 Human 运行维护授权处理安装和跨项目机械问题。项目目标归 Coordinator，产品代码归原专业作者，成员维护自己的 Current。

## 原入口恢复

核固定Home、目标Project、安装入口、Contact与原会话。修准确的定位和可用条件，保留模型、STOP及既有结果。新的原生会话由Human按需建立，不为排障重造员工。

Project员工用 `paos --json wake status <project> <agent>`，Rooter用本工位 `python contact.py status` 读取简洁的联系/配置/STOP/接收器状态；默认不读 TODO/Notice 历史，坏 TODO 不阻塞查询。需要完整 Current/Tasks/Notice 与恢复计数时用 `python contact.py status --full`。Source位置从 `paos install show` 读取。将这些正式读回值用于下方恢复步骤。

新Codex工位或换Runtime时，Rooter组织正式配置登记；目标本人按登记准备自己的接收入口。登记与只读 prepare 的步骤只读[操作指南·Codex目标上线准备](guide-paos-cat-operations.md#codex-目标上线准备)。运行细节读当前安装的 `source_root/docs/CODEX-SELF-REMINDER.md`；先用 `paos install show` 核对 `source_root`，不沿旧电脑绝对路径打开。

分别记录接收入口与原生会话状态。接收入口未就绪或未登记时，未探测的原生Runtime状态仍为未知；ThreadID登记不等于树外可达。业务与入口准备分别记录；准备受限时沿已有正式联络接续业务。

本人接收器从所属 Harness 环境启动。按当前登记维护实际运行通道；旧 Core HTTP / Bridge 保持停用。分别记录宿主、启停方法和日志；不能用某组件在线代替另一组件可用。

交付沿公共运行规则：项目成员读本项目 AGENTS；Rooter 读 System 的 Project-Template/AGENTS 公共区。通信已通但业务停止时，与原执行者/Coordinator核当前责任和停点，接续可执行工作。

## 工位位置迁移

保留身份、会话与历史，不等于保留旧物理目录。按Human指定位置搬迁真实Home，先保存Current、原件与运行入口，再同步安装登记、编号定位、原生接收、定时任务、快捷方式和当前引用。直接来源若以绝对路径派生索引，迁址时一并维护索引及处理事实，原件留恢复映射。

从新Home读Current和输入，核原会话正常接续，再将旧位置归档到库外。迁移完成以真实目录、登记和实际接续为准；只更新导航或命令不算搬迁。涉及多个Project时逐项列出真实位置和未完项，基座更新与项目/工位搬迁分别记录。

## 配置与权限

按安装描述定位Source/Library，实际版本读health；文件和进程版本分别判断。已批准配置直接执行。OpenCode权限按 [操作指南](guide-paos-cat-operations.md#工具权限与模型)，不复制审批规则。

定位OpenCode运行故障，先从正式`status`取得该Home的`base_url`与原生Session，再查对应服务和实际directory。同一Session历史可能由另一服务读到，不能据此判断执行位置。网络检查对照实际服务进程的代理配置；普通Shell直连成功只证明该Shell的连接。

外部Runtime先使用产品自带的后台运行入口。OpenCode v2用官方`service`管理后台实例；`serve`是前台专用模式，不为同一实例另造计划任务宿主。沿本机已登记的私有profile操作，保持原数据库、模型和凭据；机器路径留安装记录。冷目录先读正常模型列表完成插件初始化，再核同目录的provider和指定模型，避免把首次空表误判为账号丢失。

公开联系缺字段时沿已有Human运行授权只修明确字段。外部工具拒绝、业务越界和产品缺口分开处理；不要把一次历史错误变成永久审批。

## 发布与例外

切换与回退按 [发布采用](guide-upgrade-adoption.md)。收拢实际采用、待机和阻碍，给原责任人完整结果；不代维护成员TODO或确认本人消费。

暂停或人工入口按实际安排保留。无新业务时待自然输入，不为证明运行可用制造任务。
