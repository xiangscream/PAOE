import { FileSystemAdapter, ItemView, Notice, Plugin, WorkspaceLeaf } from 'obsidian'
import path from 'path'
import { createApp, nextTick, type App as VueApp } from 'vue'
import CatPanel from './CatPanel.vue'
import { setApiTransport } from '../../front/ui/src/api'
import { bridgeTransport } from '../shared/bridge'
import { createShadowHost, readPluginCss } from '../shared/host'
import { normalizeSettings, resolveBridge, type PaosBridgeSettings } from '../shared/settings'
import { PaosSettingsTab } from '../shared/settings-tab'
import { nativeEventSource } from '../shared/stream'
import { catRoomFromParams } from '../shared/uri'
import { vaultAliases } from '../shared/vaults'
import '../../front/ui/src/styles.css'
import '../shared/host.css'

const VIEW_TYPE = 'paos-system-cat'

class CatView extends ItemView {
  pendingRoom = ''
  private appInstance: VueApp | null = null
  private panel: any = null
  private disposeHost: (() => void) | null = null
  private readonly host: SystemCatPlugin

  constructor(leaf: WorkspaceLeaf, host: SystemCatPlugin) {
    super(leaf)
    this.host = host
  }

  getViewType(): string { return VIEW_TYPE }
  getDisplayText(): string { return 'PAOE CAT' }
  getIcon(): string { return 'messages-square' }

  async onOpen(): Promise<void> {
    this.disposeHost?.()
    this.disposeHost = null
    const content = this.contentEl
    let config
    try {
      config = this.host.bridgeConfig()
    } catch (problem) {
      this.renderError(String((problem as Error)?.message || problem))
      return
    }
    let root: HTMLElement
    try {
      const host = createShadowHost(content, readPluginCss(this.host.pluginDir))
      root = host.root
      this.disposeHost = host.dispose
    } catch (problem) {
      this.renderError(String((problem as Error)?.message || problem))
      return
    }
    this.appInstance = createApp(CatPanel, {
      project: '',
      initialRoom: this.pendingRoom,
      eventUrl: (roomId: string, cursor: number) =>
        config.catUrl.replace(/\/$/, '') + '/api/rooms/' + encodeURIComponent(roomId) + '/events?after=' + cursor,
      streamFactory: nativeEventSource,
      onNewDiscussion: () => new Notice('新讨论请从项目面板的协作/连线入口发起；System CAT 页签用于接续现有房间。'),
      onBoard: () => new Notice('项目面板在项目库中打开；当前是 System CAT。'),
    })
    this.panel = this.appInstance.mount(root)
  }

  async onClose(): Promise<void> {
    this.appInstance?.unmount()
    this.appInstance = null
    this.panel = null
    this.disposeHost?.()
    this.disposeHost = null
  }

  setRoom(roomId: string): void {
    this.pendingRoom = roomId
    if (this.panel) void this.panel.selectRoom(roomId)
  }

  private renderError(message: string): void {
    this.contentEl.textContent = ''
    const box = document.createElement('div')
    box.className = 'empty-board'
    box.innerHTML = '<h2>CAT 未就绪</h2>'
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

export default class SystemCatPlugin extends Plugin {
  settings: PaosBridgeSettings = normalizeSettings(null)
  private resolved: ReturnType<typeof resolveBridge> | null = null
  private transport: ReturnType<typeof bridgeTransport> | null = null

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
    this.registerView(VIEW_TYPE, leaf => new CatView(leaf, this))
    this.addRibbonIcon('messages-square', '打开 PAOE CAT', () => void this.openCat())
    this.addCommand({ id: 'open-paos-cat', name: '打开 PAOE CAT', callback: () => void this.openCat() })
    this.addSettingTab(new PaosSettingsTab(this.app, this, false))
    this.registerObsidianProtocolHandler('paos-cat', params => {
      const aliases = vaultAliases(this.vaultRoot())
      const parsed = catRoomFromParams(params, this.app.vault.getName(), aliases)
      if (parsed.error) {
        new Notice(parsed.error + ' 原 room_id 保留：' + String(params.room || ''))
        return
      }
      void this.openRoom(parsed.room, String(params.vault || ''))
    })
  }

  async saveSettings(): Promise<void> {
    this.resolved = null
    await this.saveData(this.settings)
  }

  bridgeConfig() {
    if (!this.resolved) {
      this.resolved = resolveBridge(this.settings)
      const adapter = this.app.vault.adapter
      if (!(adapter instanceof FileSystemAdapter)) throw new Error('当前库不是本地文件系统库。')
      this.transport = bridgeTransport({ ...this.resolved, vaultRoot: adapter.getBasePath() })
      setApiTransport(this.transport)
    }
    return this.resolved
  }

  private vaultRoot(): string {
    const adapter = this.app.vault.adapter
    if (!(adapter instanceof FileSystemAdapter)) throw new Error('当前库不是本地文件系统库')
    return adapter.getBasePath()
  }

  private samePath(a: string, b: string): boolean {
    return path.resolve(a).replace(/\\/g, '/').toLowerCase() === path.resolve(b).replace(/\\/g, '/').toLowerCase()
  }

  private async ensureSystem(): Promise<{ config: ReturnType<typeof resolveBridge>; aliases: string[] }> {
    const config = this.bridgeConfig()
    if (!this.transport) throw new Error('PAOS 桥未配置')
    const response = await this.transport('/api/obsidian/context')
    const data = await response.json()
    if (!response.ok || !data?.ok) throw new Error(data?.error || 'PAOS 桥未返回库上下文')
    if (data.kind !== 'system') throw new Error('当前库不是 System 库；CAT 只在 System 提供。')
    const root = this.vaultRoot()
    if (data.vault_root && !this.samePath(String(data.vault_root), root)) {
      throw new Error('PAOS 桥回报的 System 库路径与当前库不一致。')
    }
    return { config, aliases: vaultAliases(root) }
  }

  async openCat(): Promise<void> {
    try {
      await this.ensureSystem()
    } catch (problem) {
      new Notice('PAOE CAT 未就绪：' + String((problem as Error)?.message || problem))
      return
    }
    let leaf = this.app.workspace.getLeavesOfType(VIEW_TYPE)[0]
    if (!leaf) {
      leaf = this.app.workspace.getLeaf('tab')
      await leaf.setViewState({ type: VIEW_TYPE, active: true })
    }
    await this.app.workspace.revealLeaf(leaf)
  }

  async openRoom(roomId: string, requestedVault = ''): Promise<void> {
    if (!roomId) return
    let info
    try {
      info = await this.ensureSystem()
    } catch (problem) {
      new Notice('PAOE CAT 未就绪：' + String((problem as Error)?.message || problem))
      return
    }
    const allowed = new Set([this.app.vault.getName(), ...info.aliases])
    if (requestedVault && !allowed.has(requestedVault)) {
      new Notice(`请求的 System 库是 ${requestedVault}，当前库不是目标；room_id 保留：${roomId}`)
      return
    }
    let leaf = this.app.workspace.getLeavesOfType(VIEW_TYPE)[0]
    if (!leaf) {
      leaf = this.app.workspace.getLeaf('tab')
      await leaf.setViewState({ type: VIEW_TYPE, active: true })
    }
    const view = leaf.view as CatView
    if (view && typeof view.setRoom === 'function') view.setRoom(roomId)
    await nextTick()
    await this.app.workspace.revealLeaf(leaf)
  }
}
