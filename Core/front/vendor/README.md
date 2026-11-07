# 本地 Markdown 资产

`markdown-it-15.0.3.mjs`来自官方npm包的 `dist/browser/markdown-it.esm.min.mjs`，源码为 https://registry.npmjs.org/markdown-it/-/markdown-it-15.0.3.tgz ，MIT原许可见MARKDOWN-IT-LICENSE。未随包提供的source-map尾注已移除，解析实现保持。

统一工作台把此模块打入本地静态资源。CAT通过cat-content.mjs渲染消息及搜索标记；项目和Library文档通过ui/src/lib/markdown.ts使用同一解析器。两者均关闭原始HTML执行和自动媒体加载，前端格式化不修改原文。

Vue、Vue Flow与daisyUI沿ui/package-lock.json构建，不再保存独立浏览器版本。锁定依赖的原许可见../THIRD-PARTY-NOTICES.md；页面运行时没有CDN依赖。
