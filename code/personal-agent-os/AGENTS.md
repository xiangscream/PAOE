# PAOE 核心代码入口（兼容目录名 personal-agent-os）

正常 CLI 入口仍是 scripts/paos.py（保留 PAOS 兼容命名）。项目与工位读取直接使用本机登记和文件，不需要旧 Core HTTP 服务；CAT 和显式原生提醒是外部运行通道。

## 先读什么

开发先读 docs/DEVELOPMENT-PRINCIPLES.md。业务方法从已登记的 libraries/workflow/Guides/guide-work-method.md 按需进入；不在源码复制第二套流程。

## 代码边界

- paos_registry.py：唯一 paos-project-registry/v1 项目定位原件；显式 project register 只创建五字段登记，不覆盖、不合成旧项目管理状态。
- paos.py：参数、调用既有模块、输出结果。Project 登记写入只经 registry，Home 写入仍经各自 writer。
- paos_home.py、paos_workstation.py：固定工位定位和文件；Rooter 是安装级工位。
- paos_todo.py：现行 paos-todo/v4，Pinned 自由 Markdown + Current 小字段 + Tasks checkbox。
- paos_mail.py、paos_notice.py、paos_attention_service.py：持久输入与处理事实。
- paos_library.py：Workflow/Skill 索引、搜索与使用记录；正文是方法，不是硬状态机。
- Contact / runtime injection：显式本机绑定与一次提醒；不从迁入的旧 Project 字段恢复原生会话。

旧 session、coordinator、workbench、tips HTTP 代理和 project progress-update 不属于当前正常 CLI。历史数据未因代码收敛而自动删除。

## 验证

在包根执行：

~~~sh
python code/personal-agent-os/scripts/verify.py
~~~

验证覆盖隔离文件、核心模块、接收器模拟和语法检查，不等于生产工位、原生模型或 Windows Desktop 采用证明。真实项目、工位、凭据和生产服务不因测试被更改。
