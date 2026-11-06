# POE 统一工作台（Vue）

本目录是统一工作台的前端工程：团队画板、工位详情、Libraries 选择、主题协作与 CAT 讨论共用一个 Vue 工程。

## 运行

```text
cd Core/front/ui
npm install
npm run dev
```

Vite 默认把 `/api` 代理到 `http://127.0.0.1:8780`。联调隔离 API 时：

```powershell
$env:POE_API_TARGET = 'http://127.0.0.1:8784'
npm run dev
```

## 构建

```text
npm run build
```

`vue-tsc` 先做类型检查，随后 Vite 输出到 `Core/front/dist/`。`dist` 由现有 Python 本地服务直接提供，不需要 Node 常驻进程；接口始终是同源 `/api`。

## 测试

```text
npm test
```

覆盖布局合并与视口边界、协作表单校验与稳定 message_id、未知结果不重发、CAT 消息游标、草稿按房间保存、成员暂停状态和人员卡片渲染。

## 边界

- 前端只读 `/api/*` 投影，不直接读写文件，不保存第二份团队、任务或消息状态。
- 位置与视口只保存布局；拖动与连线不改团队关系。
- 业务写入全部经现有接口：Mail 复用 `agent send`，Chat 复用 CAT 建/入/发，提醒沿原唤醒器。
- 保存、提醒受理和对方接手分别显示；未知结果保留原请求，只读核对，不自动重发。
