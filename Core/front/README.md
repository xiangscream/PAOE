# Portable 画板

画板沿用 WorkBuddy/S040 的拖动节点与侧栏原型，连接当前 Portable 文件底座。
服务使用 Python 标准库。画板沿用原生 JavaScript；独立 CAT 使用本地 Vue 3 与 daisyUI，运行不需 Node 服务或构建步骤。

## 打开

先按包根 README 完成 `portable.py init`、项目登记和真实 Home 准备，然后运行：

```text
python portable.py serve
```

浏览器访问 `http://127.0.0.1:8780/`。需要其他端口或显式安装描述时：

```text
python portable.py serve --port 8781 --installation-file <本机安装描述的绝对路径>
```

默认配置是此 checkout 的 `config/local/installation.json`，不读取旧原型的盘符，
也不依赖当前 shell 工作目录或 WorkBuddy 自带 Python。解释器使用启动画板的 Python。
机器没有迁入项目时会显示空安装说明，不从相邻目录猜工位。

开发与 CI 可用 `node --test tests/board-ui.test.mjs` 检查显示转义及结果未知时的重发控制；
运行画板和文件 CLI 不需要 Node。

## 看什么、做什么

- 下拉菜单只列当前安装登记的项目，成员和 Coordinator 来自同一登记原件。
- 当前画板成员是项目登记的 Home；Rooter 仍使用安装级联络入口，没有项目内的右键留信节点。
- 节点可拖动；节点与详情读取实际 TODO v4，显示下一步、任务统计和原文。
- Notice 统计使用现有合并读面，含 `.handled` 处理事实，不按登记文件数量推算。
- 右键选择共享方法，可向该 Agent 持久留信；此动作不自动请求原生提醒。
- 项目页读取已有 `INDEX.md`，不维护第二份项目进度或 Workbench 状态。
- 前端没有工位写者、任务引擎或后台消费者；动作通过已安装 CLI 执行。

## 可选 CAT

```text
python portable.py serve --cat-url http://127.0.0.1:8870
```

这只连接已有 CAT，不安装或启动它。未配置或连接失败会直接显示原因，文件功能继续工作。
Ctrl 多选两个或更多工位后，点击“围绕主题沟通”建立圆桌；消息使用原 CAT 的成员、
保存和单次提醒路径。发言者为页面使用者 `human`，不冒充某个 Agent。

消息保存、提醒受理与实际消费分别成立。超时保持结果未知，不自动重新提交。
结果未知时发送按钮暂停，使用“核对消息”读取原房间；输入不会自动重投。
连线是画板布局，业务事实在 CAT；页面刷新后仍可从房间列表进入原讨论。
画板监听仅为 `127.0.0.1`，退出该进程即可关闭，不注册任何开机任务。

## 独立 CAT 聊天室

沿同一个 `portable.py serve` 入口显式设置安装描述和已有 CAT：

```text
python portable.py serve --installation-file <现有安装描述> --cat-url http://127.0.0.1:8870
```

打开 `http://127.0.0.1:8780/cat`，或从画板顶部进入。可用 `?room=<房间ID>` 直接打开已有讨论。
页面展示房间名称、既有成员显示名和参与/旁听/离席状态；这些是席位状态，不表示原生会话在线。
消息按序号排列并显示时间，可以回复原消息。页面通过配对 CAT 的 `/events` SSE 入口接收增量；
切到后台时关闭读取，回来按已读序号补读。实时接口不可用会明确显示连接中断，不伪称实时。
发送仍用原 CLI 与 CAT POST，浏览器不轮询模型，也不直接写 JSON。

左侧可新建讨论并从现行登记选择同事；进行中与已结束房间按真实状态分组。
底部外观选择提供简洁、深色、商务、复古；只切换主题，保留当前消息、草稿与回复对象。
Vue Options API 位于 `cat.mjs`，模板在 `cat.html`，布局在 `cat.css`；依赖来源和 MIT 许可在 `vendor/`。

网页固定以 `human` 发言，首次发送通过原 CAT join 入席，不要求输入 Home ID 或选择 Agent 署名。
已有旁听、离席及关闭房间的限制保持；不会通过重复 join 自动恢复参与。Agent 继续通过自己的 CLI 身份协作。
消息保存与提醒排队分别显示；发送结果未知时保留输入并暂停再次提交，使用“核对原消息”读取保存事实。
核对是只读操作，不重发原文。页面及响应不包含运行凭据。

相关边界检查：`python -m unittest discover -s tests -p test_cat_board.py`，
`node --test tests/cat-ui.test.mjs`。验收真实房间时，Human 提交由本人操作；自动写入检查使用隔离数据。

## 换电脑

重新取得本仓库，在新机生成安装定位，登记选定的项目和 Home，按新机实际环境配置可选 CAT。
画板使用同一命令启动。原生会话、登录、接收器和 STOP 继续按迁移边界单独处理；
能看到节点不代表员工在线或已收到提醒。
