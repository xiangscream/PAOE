import { build } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from 'tailwindcss'
import autoprefixer from 'autoprefixer'
import path from 'node:path'
import { writeFileSync, readFileSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const core = path.resolve(here, '..', '..')
const obsidian = path.join(core, 'obsidian')
const tailwindConfig = (await import(pathToFileURL(path.join(here, 'tailwind.config.js')).href)).default
const plugins = ['project-panel', 'system-cat']

for (const name of plugins) {
  await build({
    root: here,
    configFile: false,
    plugins: [vue()],
    resolve: {
      alias: [
        { find: /^vue$/, replacement: path.join(here, 'node_modules', 'vue') },
        { find: /^@vue-flow\/core$/, replacement: path.join(here, 'node_modules', '@vue-flow', 'core') },
        { find: /^@vue-flow\/core\/(.*)$/, replacement: path.join(here, 'node_modules', '@vue-flow', 'core', '$1') },
      ],
    },
    css: {
      postcss: {
        plugins: [
          tailwindcss({
            ...tailwindConfig,
            content: [path.join(here, 'index.html'), path.join(here, 'src/**/*.{vue,ts}')],
          }),
          autoprefixer(),
        ],
      },
    },
    build: {
      outDir: path.join(obsidian, name),
      emptyOutDir: false,
      cssCodeSplit: false,
      minify: 'esbuild',
      lib: {
        entry: path.join(obsidian, name, 'main.ts'),
        formats: ['cjs'],
        fileName: () => 'main.js',
        cssFileName: 'paos-ui',
      },
      rollupOptions: {
        external: ['obsidian', 'electron', 'fs', 'path', 'os', 'child_process', 'http', 'https', /^node:/],
        output: {
          entryFileNames: 'main.js',
          chunkFileNames: '[name].js',
          assetFileNames: asset => asset.name?.endsWith('.css') ? 'paos-ui.css' : '[name][extname]',
        },
      },
    },
  })
  writeFileSync(
    path.join(obsidian, name, 'styles.css'),
    '.paos-obsidian-host{height:100%;min-height:0;overflow:hidden}\n',
    'utf8',
  )
  const bundle = path.join(obsidian, name, 'main.js')
  writeFileSync(bundle, readFileSync(bundle, 'utf8').replace(/[ \t]+$/gm, ''), 'utf8')
  console.log('built', name)
}
