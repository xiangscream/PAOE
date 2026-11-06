# CAT local frontend dependencies

markdown-it 15.0.3: official npm package, dist/browser/markdown-it.esm.min.mjs; MIT, see MARKDOWN-IT-LICENSE. Source: https://registry.npmjs.org/markdown-it/-/markdown-it-15.0.3.tgz . The pinned browser module is served locally; raw HTML and automatic media loading are disabled in cat-content.mjs. Only HTTP(S) links are clickable.

Vue 3.5.45: official npm vue package, dist/vue.esm-browser.prod.js; MIT, see VUE-LICENSE.

daisyUI 5.7.50: official npm daisyui package; selected base styles, button/input/textarea/select/badge/tab/modal/checkbox/menu components, light/dark/corporate/retro themes; MIT, see DAISYUI-LICENSE.

Sources: https://registry.npmjs.org/vue/-/vue-3.5.45.tgz and https://registry.npmjs.org/daisyui/-/daisyui-5.7.50.tgz . The CSS is a concatenation of these published CSS files, not a runtime CDN dependency. No package install scripts were run. The page and Core CLI require no Node server or frontend build to run. Vue's Options API is used in ../cat.mjs; template in ../cat.html, layout in ../cat.css, message invariants in ../cat-state.mjs. Theme changes only set data-theme and save a browser UI preference.
