import { FileSystemAdapter, ItemView, Notice, Plugin, WorkspaceLeaf } from 'obsidian'
import path from 'path'
import { createApp, type App as VueApp } from 'vue'
import ProjectPanel from './ProjectPanel.vue'
import { setApiTransport } from '../../front/ui/src/api'
import { bridgeTransport } from '../shared/bridge'
import { createShadowHost, readPluginCss } from '../shared/host'
import { normalizeSettings, resolveBridge, type PaosBridgeSettings } from '../shared/settings'
import { PaosSettingsTab } from '../shared/settings-tab'
import { buildCatUri } from '../shared/uri'
import '../../front/ui/src/styles.css'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '../shared/host.css'

const VIEW_TYPE = 'paos-project-panel'

class ProjectView extends ItemView {
  private appInstance: VueApp | null = null
  private disposeHost: (() => void) | null = null
  private readonly host: ProjectPlugin

  constructor(leaf: WorkspaceLeaf, host: ProjectPlugin) {
    super(leaf)
    this.host = host
  }

  getViewType(): string { return VIEW_TYPE }
  getDisplayText(): string { return 'PAOE 项目面板' }
  getIcon(): string { return 'layout-dashboard' }

  async onOpen(): Promise<void> {
    this.disposeHost?.()
    this.disposeHost = null
    const content = this.contentEl
    let root: HTMLElement
    try {
      const css = readPluginCss(this.host.pluginDir)
      const host = createShadowHost(content, css)
      root = host.root
      this.disposeHost = host.dispose
    } catch (problem) {
      this.renderError(String((problem as Error)?.message || problem))
      return
    }
    try {
      const context = await this.host.context()
      if (context.kind !== 'project') throw new Error('当前库不是已登记的项目库；请打开项目库使用项目面板。')
      this.appInstance = createApp(ProjectPanel, {
        project: context.project,
        projectName: '',
        openCat: (roomId: string) => this.host.openCat(roomId),
      })
      this.appInstance.mount(root)
    } catch (problem) {
      this.disposeHost?.()
      this.disposeHost = null
      this.renderError(String((problem as Error)?.message || problem))
    }
  }

  async onClose(): Promise<void> {
    this.appInstance?.unmount()
    this.appInstance = null
    this.disposeHost?.()
    this.disposeHost = null
  }

  private renderError(message: string): void {
    this.contentEl.textContent = ''
    const box = document.createElement('div')
    box.className = 'empty-board'
    box.innerHTML = '<h2>项目面板未就绪</h2>'
    const detail = document.createElement('p')
    detail.textContent = message
    const retry = document.createElement('button')
    retry.className = 'btn'
    retry.textContent = '重试'
    retry.addEventListener('click', () => void this.onOpen())
    box.append(detail, retry)
    this.contentEl.append(box)
  }
}

export default class ProjectPlugin extends Plugin {
  settings: PaosBridgeSettings = normalizeSettings(null)

  get pluginDir(): string {
    const dir = String((this.manifest as any).dir || '')
    if (!dir) throw new Error('插件目录不可用：manifest.dir 为空')
    if (path.isAbsolute(dir)) return dir
    const adapter = this.app.vault.adapter
    if (!(adapter instanceof FileSystemAdapter)) throw new Error('当前库不是本地文件系统库')
    return path.join(adapter.getBasePath(), dir)
  }

  async onload(): Promise<void> {
    this.settings = normalizeSettings(await this.loadData())
    this.registerView(VIEW_TYPE, leaf => new ProjectView(leaf, this))
    this.addRibbonIcon('layout-dashboard', '打开 PAOE 项目面板', () => void this.openPanel())
    this.addCommand({ id: 'open-paos-project-panel', name: '打开 PAOE 项目面板', callback: () => void this.openPanel() })
    this.addSettingTab(new PaosSettingsTab(this.app, this, true))
    this.app.workspace.onLayoutReady(() => void this.openIfProjectVault())
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings)
  }

  async context(): Promise<Record<string, any>> {
    const resolved = resolveBridge(this.settings)
    const transport = bridgeTransport({ ...resolved, vaultRoot: this.vaultRoot() })
    setApiTransport(transport)
    const response = await transport('/api/obsidian/context')
    const data = await response.json()
    if (!response.ok || !data?.ok) throw new Error(data?.error || 'PAOS 桥未返回项目上下文')
    return data
  }

  async openIfProjectVault(): Promise<void> {
    try {
      const context = await this.context()
      if (context.kind === 'project') await this.openPanel()
    } catch (problem) {
      new Notice('PAOE 项目面板未自动打开：' + String((problem as Error)?.message || problem))
    }
  }

  async openPanel(): Promise<void> {
    let leaf = this.app.workspace.getLeavesOfType(VIEW_TYPE)[0]
    if (!leaf) {
      leaf = this.app.workspace.getLeaf('tab')
      await leaf.setViewState({ type: VIEW_TYPE, active: true })
    }
    await this.app.workspace.revealLeaf(leaf)
  }

  openCat(roomId: string): void {
    const vault = this.settings.systemVault.trim()
    if (!vault) {
      new Notice('请先在 PAOE 项目面板设置中填写 System 库名称或 ID。')
      return
    }
    const uri = buildCatUri(vault, roomId)
    const opened = window.open(uri, '_blank')
    if (!opened) new Notice('无法请求打开 System CAT。可直接打开 URI：' + uri)
  }

  private vaultRoot(): string {
    const adapter = this.app.vault.adapter
    if (adapter instanceof FileSystemAdapter) return adapter.getBasePath()
    throw new Error('当前库不是本地文件系统库，无法使用 PAOS 桥。')
  }
}
