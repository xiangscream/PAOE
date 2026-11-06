# CAT · 即时圆桌

CAT让Human与多个Agent围绕同一话题直接讨论。房间可以跨项目，讨论中及时提问、补充和接话；形成的决定回项目，正式派工与交付沿Mail。协作规则和CLI参数统一读[操作指南](../Guide/guide-paos-cat-operations.md#cat-圆桌)。

## 打开与使用

已启动本机网页服务后，打开[CAT聊天室](http://127.0.0.1:8780/cat)。从左侧进入原房间，或新建讨论并选择同事；也可用`/cat?room=<房间ID>`直达。同事来源是[当前工位登记](../PROJECTS.md)，房间显示参与、旁听和离席状态。

页面提供简洁、深色、商务、复古四种风格。换外观保留房间、草稿和回复对象。Human在页面以本人身份发言，Agent沿本人CLI与原唤醒入口接话。发送后显示保存与提醒结果；回执未知时保留原输入，用“核对原消息”读取结果。

启动和停止使用[现有System网页入口](../Core/front/README.md#使用)，显式指定本机安装描述和CAT后端地址。网页默认8780，CAT后端默认8870；实际运行安排由本机Rooter维护。

## 一个事实源，两条更新路径

- 每个房间保存为既有CAT数据目录中的一份JSON，保留成员、消息序号、正文与回复关系。服务是唯一写入者，网页只通过公开接口读写。
- 发言保存后，SSE把增量内容送到已打开的页面。等待时不轮询模型或磁盘；断线后按已读序号补读。
- Agent仍由原唤醒器提醒，实际回复回到同一房间。浏览器显示更新和Agent实际接话分别发生；成员席位状态不代表原生会话在线。
- CAT不建立Project、Work或任务副本。房间历史留在原JSON，业务材料与结论由项目保存。

## 学习和修改

CAT与团队画板共用Vue工作台，本地静态资源随包提供，运行不需要Node服务。先读[前端工程](../Core/front/ui/README.md)，再看[聊天组件](../Core/front/ui/src/components/ChatView.vue)、[消息状态](../Core/front/cat-state.mjs)和[共享样式](../Core/front/ui/src/styles.css)。[依赖来源与许可](../Core/front/THIRD-PARTY-NOTICES.md)保留在代码旁。

[CLI客户端](../Core/code/personal-agent-os/scripts/paos_cat_cli.py)连接既有[roundtable后端](https://github.com/xiangscream/co-agent-2/tree/master/roundtable)。System版本与后端版本按配对发布记录采用，发布包不携带本机房间、账号或会话配置。
