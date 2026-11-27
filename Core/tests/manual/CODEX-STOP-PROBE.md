# Desktop 连续 Stop 宿主实测

本入口只准备有限实验，不证明宿主已经通过。它不连接 PAOE 生产 Data、TODO、Contact 或 CAT，不准备接收器，不启动应用，不更换模型。

1. 在独立 Desktop 项目中使用正常项目级 `.codex/hooks.json`，由应用正常审阅信任。保留用户全局 Hook 原样，不修改信任缓存。先取得准确的专用测试会话 ID；不是 S052 或其他生产业务会话。
2. 唯一项目级 Stop command 使用本目录 `codex_stop_probe.py --session <准确ID> --evidence <本次新JSONL绝对路径> --stop-file <本次STOP绝对路径>`。使用本机既有 Python，命令路径加引号。其余 Hook 不添加。配置的形状与[官方文档](https://learn.chatgpt.com/docs/hooks#stop)一致：`{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"<上述完整命令>","timeout":10}]}]}}`。

   可给同一命令追加 `--write-project-config <隔离项目目录>`，一次生成准确命令与项目配置。它只新建，不覆盖配置，不登记信任。生成后须由应用按正常入口审阅；不能绕过或复制信任。此准备动作不算真实宿主试验。
3. 检查叠加的用户 Hook 对该未登记测试会话为 noop，不存在其他 `continue:false`。同一会话发一次简单请求后结束：观察真实 Stop 记录、A 提示及实际续回合、active=true 的第二次 Stop、B 提示及实际续回合，最后第三次正常停止。保留宿主回合的原记录定位。
4. 文件仅记录 session/turn/事件/active 和完整控制输出，不收集业务正文或凭据。第二轮用新证据文件，不能清空后把重放冒充新事件。

两次返回 block 后第三次正常结束是有限实验协议，不是业务续工次数上限。不同会话及 STOP 存在时返回空对象。若缺少第二次原生事件，分别排除未信任、其他 Hook 拒绝、适配器执行失败和宿主行为；不能只凭“没有下一回合”宣告宿主上限。此脚本的合成单测只验记录合同，真实通过必须来自 Desktop。
