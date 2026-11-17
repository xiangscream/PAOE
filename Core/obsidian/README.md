# PAOE Obsidian 插件包

首版包含两个独立插件，共用同一套 Vue 组件与单次进程桥：

- `project-panel/`：项目库打开后显示本项目团队画板。
- `system-cat/`：System 库提供原生 CAT 页签。

源码入口在各目录 `main.ts`，构建产物 `main.js`、`paos-ui.css`、`manifest.json`、`styles.css` 同目录。真实安装由 Rooter 执行，执行者不直接投放真实库。

## 宿主隔离

- Obsidian 自动载入的 `styles.css` 只有 `.paos-obsidian-host{height:100%;...}`。
- 完整 UI 样式在 `paos-ui.css`，由插件读取后注入每个视图的 shadow root；不把 `html/body/*`、Tailwind/Daisy 规则挂到 Obsidian 全局。
- 视图卸载时同时卸载 Vue 实例、主题观察器、SSE 和 resize/visibility 监听。

## 设置

两个插件都需要：

- Python 可执行文件：安装者保存的真实 `python.exe`。
- 安装描述：默认 `~/.paos/installation.json`。
- PAOS 桥路径：留空时从安装描述 `source_root` 推导 `Core/front/paos_obsidian_bridge.py`。
- CAT 后台地址：默认 `http://127.0.0.1:8870`。

项目面板另需 System 库名称或 ID，用于 `obsidian://paos-cat` 的 `vault` 参数。使用真实 System 库名或 Obsidian 的 16 位库 ID；不要填绝对路径。

## 使用

- 项目库：插件在 layout ready 后调用 `/api/obsidian/context`，确认当前库是已登记项目后打开面板。画板拖动、布局保存、Library 右键、连线 Mail/Chat 都走原桥和原 writer。
- System 库：命令/ribbon 打开 CAT；项目面板发起 Chat 后，以 `obsidian://paos-cat?vault=<System库名或ID>&room=<room_id>` 请求 System 库打开同一 CAT 页签并定位房间。
- CAT 页签不加载 8780 网页；数据走桥，实时流直接连原 CAT 后台 `/api/rooms/<room_id>/events?after=<cursor>`。
- 桥失败、未知提交、房间不含当前库时保留原 room_id/message_id，不伪造成功、不自动重发。

## 构建

在 `Core/obsidian` 下：

```text
node build.mjs
```

脚本使用 Vite + Vue 编译两个入口，业务构建依赖来自既有 `Core/front/ui/node_modules`，不会启动常驻服务。构建后必须保留各目录的 `manifest.json`、`styles.css`、`paos-ui.css` 和 `main.js`。

`types/obsidian.d.ts` 是官方 `obsidian-api` 的 `obsidian.d.ts`，仅用 `types/node-shims.d.ts` 补 Node 内置模块与 CodeMirror 类型占位；`vue-tsc -p Core/obsidian/tsconfig.json` 按官方 SDK 类型检查宿主。

## 已知边界

- CAT 页签的“新建讨论”按钮当前提示从项目面板发起；首版把开聊入口留在项目面板，避免在 System 库重新建立项目归属。
- 跨库 URI 的 System 已打开/未打开两条路径、真实 vault ID 与真实库安装仍需 S031/S063/Rooter 在原生 Obsidian 验收。
- 桥 24d7c38 的阶段结果由 S031 集成；本目录不复制桥实现。
