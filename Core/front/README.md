# POE 本地工作台

一个本地入口呈现团队画板、参考库、项目文档和 CAT 讨论。姓名、职责与成员状态来自 TEAM，当前行动来自工位 TODO，消息仍由现有 Mail/CAT 保存。关闭网页后，Agent 继续使用原文件、CLI 和唤醒器。

## 使用

按 Core README 准备本机安装与项目登记后，运行：

```text
python portable.py serve --installation-file <本机安装描述> --cat-url http://127.0.0.1:8870
```

浏览器打开 `http://127.0.0.1:8780/`。现有 `/cat` 和 `/cat?room=<房间ID>` 链接进入同一工作台的讨论页。`--port` 可指定其他端口。服务只监听127.0.0.1，退出进程即可关闭；此命令连接已有CAT，不另启后台消费者。

- 拖动卡片、平移和缩放可调整画布；位置及视口按项目保存到 `.paos/ui/board.json`。
- 从提供方A向需要补充的B连线，填写主题，选择临时讨论或邮件，确认预览后提交。连线不修改团队关系。
- 右键卡片或点右上角按钮可搜索、预览全部已登记的Workflow/Skill/Tool。范例可附到当前协作，也可单独给同事留参考信；单独参考默认不提醒。
- 临时讨论复用普通CAT房间，Human首条消息包含主题、双方和参考来源；邮件以Human向A、B双方留信。提醒沿原入口，未配置或失败会如实显示。
- 未接入及暂停成员可阅读资料，联系动作受其原状态限制。页面不把Contact配置当作在线，也不修改模型、会话、Contact或STOP。
- 项目概览读取INDEX和TEAM，项目内文档链接可继续阅读；工位详情显示行动、任务和最近邮件。Library与项目外的文件位置可复制到原工作环境打开。

## 讨论与接续

CAT支持Markdown、长文展开、引用、同桌抽屉、搜索定位和回到最新。Ctrl/⌘+Enter发送，输入框随内容增高；消息通过原SSE连接更新。进行中、结束、参与、旁听和离席均来自原房间。

草稿、回复对象与未确认的提交只保存在当前浏览器，用于恢复输入；消息事实仍从CAT或Mail读取。保存、提醒受理与Agent实际接手分别成立。结果未知时保留原编号，只读核对；已知建房部分完成可显式继续原房间。切页与刷新不会自动重发。

CAT未配置或连接中断时，文件、团队和项目文档仍可使用。默认主题为简洁，也可统一切换深色、商务和复古。坐标、主题和显示偏好只影响呈现，不另建业务状态库。

## 开发与发行

[前端工程](ui/README.md)采用Vue 3、TypeScript、Vite、Vue Flow和daisyUI。构建输出位于 `dist/`，随Git发行包一同交付；正常运行只需现有Python服务，无需Node常驻、CDN或外网资源。

`paos_front_server.py`提供文件读面、布局写口，以及对已有CLI的薄组合接口。它不拥有工位TODO或Agent推理循环。CAT内容与游标/回执纯函数位于 `cat-content.mjs`、`cat-state.mjs`；消息组件位于 `ui/src/components/ChatView.vue`。旧独立画板和CAT启动页面已统一替换。

测试使用隔离项目及记录器，不连接真实模型或发送生产测试消息。Python边界测试位于 `Core/tests/test_board.py`、`test_cat_board.py`；Vue组件和状态测试位于 `ui/tests/`。依赖原许可见 [THIRD-PARTY-NOTICES](THIRD-PARTY-NOTICES.md)与 [vendor](vendor/README.md)。
