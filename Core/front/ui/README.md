# POE 统一工作台前端

团队画板、详情、Libraries、协作表单与CAT使用同一Vue工程。画布读取TEAM和工位摘要，文档按需读取原件，主题协作复用Mail/CAT；前端不直接写文件或调用模型。

本地验证使用Node 24。在本目录执行：

```text
npm ci
npm run build
npm test
```

`package-lock.json`固定依赖版本。`build`先执行类型检查，再生成 `../dist/`；生成的HTML、JS与CSS是发行内容，不提交node_modules。开发时用 `npm run dev`，默认代理隔离接口 `http://127.0.0.1:8784`；需要其他已准备的本地接口时显式设置 `POE_API_TARGET`，不要把写入测试指向生产项目。

```powershell
$env:POE_API_TARGET = 'http://127.0.0.1:8784'
npm run dev
```

主壳在App.vue；BoardCanvas负责布局和连线手势，CollaborationDialog维护一次主题请求，ChatView承接已验收的CAT阅读与发送交互。DocView共享原文阅读样式，Markdown沿用本地 `../vendor/markdown-it-15.0.3.mjs`。该资产已有许可证，无需再写解析器或安装第二份。

组件测试覆盖暂停成员、主题双方、不可变提交、未知结果刷新、已知partial继续、卸载后的请求边界与文档导航。Core目录还可运行：

```text
node --test tests/cat-ui.test.mjs tests/cat-content.test.mjs tests/cat-drafts.test.mjs
python -m unittest discover -s tests -p test_*board.py
```

正常使用部署好的静态包不需要Node。业务文件、消息、模型和Agent执行都可脱离网页继续运行。
