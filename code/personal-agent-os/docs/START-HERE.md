# PAOE 开始：当前 Portable 基线

本页是代码学习与重新进入仓库的导航。安装与迁移的完整步骤见仓库根目录 README.md 和 MIGRATION-NOTES.md；不要使用早期 PAOS Core / Session / Dashboard 的启动说明。

## 先理解系统

1. [README：产品定位与安装入口](../../../README.md)
2. [ARCHITECTURE：当前系统与事实边界](../../../ARCHITECTURE.md)
3. [DOMAIN-MODEL：当前对象模型](DOMAIN-MODEL.md)
4. [CODE-MAP：代码位置与调用链](CODE-MAP.md)
5. [DEVELOPMENT-PRINCIPLES：开发准则](DEVELOPMENT-PRINCIPLES.md)
6. [LEARNING-BASELINE：学习路线与练习边界](../../../LEARNING-BASELINE.md)

## 只读检查

在仓库根目录执行：

~~~sh
python portable.py plan
python portable.py doctor
python code/personal-agent-os/scripts/paos.py --help
~~~

plan 和 doctor 不创建业务对象。doctor 只检查安装定位，不证明 CLI 业务、真实 Home 或 Runtime 已经可用。

## 运行隔离测试

~~~sh
python code/personal-agent-os/scripts/verify.py
node --test tests/board-ui.test.mjs
~~~

测试使用隔离目录和模拟接收器，不需要连接生产 Home、CAT 或真实模型。学习代码时优先从测试 fixture 了解输入与预期结果。

## 启动可选画板

只有本机已经完成 portable.py init、登记现有 Project，并且对应 Home 文件准备好后，才运行：

~~~sh
python portable.py serve
~~~

浏览器访问 http://127.0.0.1:8780/。画板不是 CLI 的前置服务；不启动画板也可以学习和使用文件 CLI。CAT 需要单独配置，不会由画板自动安装或启动。

## 重要边界

- Project Registry 只保存定位，不是项目事实数据库。
- Project Vault 的 INDEX.md、TEAM.md、材料和成果是项目原件。
- Agent 的当前责任在固定 Home 的 TODO v4。
- Mail、Notice、提醒、实际接手和任务完成是不同事实。
- Workflow / Skill / Tool 正文以已登记 Library 的源文件为准；随包文件不代表本机已经采用。
- Rooter 是安装级 Home，不属于某个 Project。
- 不要把旧 Session、Work、Cycle、ProjectStore 或旧 Dashboard 文档当作当前运行模型。

第一次学习建议从 LEARNING-BASELINE.md 的 M0 开始，不要直接修改生产数据。
