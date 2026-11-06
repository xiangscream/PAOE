# 项目与 Agent

这是发布中的中性入口，不含任何机器的项目、成员、路径或绑定。已有安装保留本机生成页；新安装按自己的 Registry、TEAM、ENTRY 重建。

## 外部唤醒

先由本机聚合页定位成员；实际绑定和 STOP 以 Contact 为准。发布源不携带可唤醒的原生 Session。

## 更新与检查

在 System 根目录，使用本机实际安装描述：

```text
python -X utf8 -B Core/code/personal-agent-os/scripts/paos_team_overview.py --installation-file Core/config/local/installation.json --output PROJECTS.md --write
python -X utf8 -B Core/code/personal-agent-os/scripts/paos_team_overview.py --installation-file Core/config/local/installation.json --output PROJECTS.md --check
```

生成后的页面属于本机部署状态。发布构建从干净 Git 提交读取中性原件，不打包机器生成页。
