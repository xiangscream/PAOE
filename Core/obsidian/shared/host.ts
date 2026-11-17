import { readFileSync } from 'fs'
import path from 'path'

export function readPluginCss(pluginDir: string): string {
  return readFileSync(path.join(pluginDir, 'paos-ui.css'), 'utf8')
}

export function createShadowHost(container: HTMLElement, css: string): { root: HTMLElement; dispose: () => void } {
  const host = document.createElement('div')
  host.className = 'paos-obsidian-host'
  host.style.height = '100%'
  const shadow = host.attachShadow({ mode: 'open' })
  const style = document.createElement('style')
  style.textContent = css
  const root = document.createElement('div')
  root.className = 'paos-obsidian-root'
  root.dataset.theme = currentTheme()
  shadow.append(style, root)
  container.append(host)
  const observer = new MutationObserver(() => { root.dataset.theme = currentTheme() })
  observer.observe(document.body, { attributes: true, attributeFilter: ['class'] })
  return {
    root,
    dispose: () => {
      observer.disconnect()
      host.remove()
    },
  }
}

function currentTheme(): string {
  if (document.body.classList.contains('theme-dark')) return 'dark'
  if (document.body.classList.contains('theme-light')) return 'light'
  return 'light'
}
