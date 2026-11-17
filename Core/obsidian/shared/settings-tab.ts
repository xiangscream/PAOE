import { App, Plugin, PluginSettingTab, Setting } from 'obsidian'
import type { PaosBridgeSettings } from './settings'

export interface SettingsOwner extends Plugin {
  settings: PaosBridgeSettings
  saveSettings(): Promise<void>
}

export class PaosSettingsTab extends PluginSettingTab {
  private readonly owner: SettingsOwner
  private readonly showSystemVault: boolean

  constructor(app: App, owner: SettingsOwner, showSystemVault = false) {
    super(app, owner)
    this.owner = owner
    this.showSystemVault = showSystemVault
  }

  display(): void {
    const { containerEl } = this
    containerEl.empty()
    new Setting(containerEl)
      .setName('Python 可执行文件')
      .setDesc('安装者保存的真实 python.exe；桥按此路径启动，不经 shell。')
      .addText(text => text.setValue(this.owner.settings.pythonPath).onChange(async value => {
        this.owner.settings.pythonPath = value.trim()
        await this.owner.saveSettings()
      }))
    new Setting(containerEl)
      .setName('安装描述')
      .setDesc('本机 ~/.paos/installation.json 的准确路径。')
      .addText(text => text.setValue(this.owner.settings.installationFile).onChange(async value => {
        this.owner.settings.installationFile = value.trim()
        await this.owner.saveSettings()
      }))
    new Setting(containerEl)
      .setName('PAOS 桥路径（可选）')
      .setDesc('留空时从安装描述的 source_root 推导 Core/front/paos_obsidian_bridge.py。')
      .addText(text => text.setValue(this.owner.settings.bridgePath).onChange(async value => {
        this.owner.settings.bridgePath = value.trim()
        await this.owner.saveSettings()
      }))
    new Setting(containerEl)
      .setName('CAT 后台地址')
      .setDesc('原 CAT 后台，默认 http://127.0.0.1:8870；项目文件读取不依赖它。')
      .addText(text => text.setValue(this.owner.settings.catUrl).onChange(async value => {
        this.owner.settings.catUrl = value.trim()
        await this.owner.saveSettings()
      }))
    if (this.showSystemVault) {
      new Setting(containerEl)
        .setName('System 库名称或 ID')
        .setDesc('开聊时用于 obsidian://paos-cat 的 vault 参数；必须绑定真实 System 库，不能猜绝对路径。')
        .addText(text => text.setValue(this.owner.settings.systemVault).onChange(async value => {
          this.owner.settings.systemVault = value.trim()
          await this.owner.saveSettings()
        }))
    }
  }
}
