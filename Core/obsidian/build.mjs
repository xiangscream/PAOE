import { build } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from 'tailwindcss'
import autoprefixer from 'autoprefixer'
import path from 'node:path'
import { writeFileSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const front = path.resolve(here, '..', 'front', 'ui')
const tailwindConfig = (await import(pathToFileURL(path.join(front, 'tailwind.config.js')).href)).default

const plugins = ['project-panel', 'system-cat']

for (const name of plugins) {
  await build({
    root: here,
    configFile: false,
    plugins: [vue()],
    css: {
      postcss: {
        plugins: [
          tailwindcss({
            ...tailwindConfig,
            content: [path.join(front, 'index.html'), path.join(front, 'src/**/*.{vue,ts}')],
          }),
          autoprefixer(),
        ],
      },
    },
    build: {
      outDir: path.join(here, name),
      emptyOutDir: false,
      cssCodeSplit: false,
      minify: 'esbuild',
      lib: {
        entry: path.join(here, name, 'main.ts'),
        formats: ['cjs'],
        fileName: () => 'main.js',
        cssFileName: 'paos-ui',
      },
      rollupOptions: {
        external: ['obsidian', 'electron', 'fs', 'path', 'os', 'child_process', /^node:/],
        output: {
          entryFileNames: 'main.js',
          chunkFileNames: '[name].js',
          assetFileNames: asset => asset.name?.endsWith('.css') ? 'paos-ui.css' : '[name][extname]',
        },
      },
    },
  })
  writeFileSync(
    path.join(here, name, 'styles.css'),
    '.paos-obsidian-host{height:100%;min-height:0;overflow:hidden}\n',
    'utf8',
  )
  console.log('built', name)
}
