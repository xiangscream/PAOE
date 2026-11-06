"""Resolve this registered Home, then call the installed PAOE implementation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def context(installation_file: str):
    if not installation_file:
        raise ValueError("设置 PAOS_INSTALLATION_FILE 或传 --installation-file；路径见本人 ENTRY。")
    installation = Path(installation_file).expanduser()
    if not installation.is_absolute():
        raise ValueError("installation-file 必须是绝对路径。")
    raw = json.loads(installation.read_text(encoding="utf-8-sig"))
    source = Path(raw.get("source_root", ""))
    scripts = source / "scripts"
    if not source.is_absolute() or not (scripts / "paos.py").is_file():
        raise ValueError("安装描述中的 source_root 无法定位当前 PAOE 代码。")
    sys.path.insert(0, str(scripts))
    from paos_installation import load_installation_descriptor
    from paos_registry import ProjectRegistry
    from paos_home import agent_project_id, project_agent_home

    descriptor = load_installation_descriptor(installation)
    home = Path(__file__).resolve().parent.parent
    project_id = agent_project_id(home.name)
    project = ProjectRegistry(installation).read(project_id)
    ref = project_agent_home(project=project, agent_id=home.name)
    if home != Path(ref["home_path"]).resolve():
        raise ValueError("脚本目录与 Registry 中本人工位不一致；母版不可直接绑定。")
    return installation, descriptor, scripts, home, ref


def execute(driver: str, args) -> int:
    installation, descriptor, scripts, home, ref = context(args.installation_file)
    env = {**os.environ, "PAOS_INSTALLATION_FILE": str(installation)}
    prefix = [sys.executable, "-X", "utf8", "-B"]
    cli = prefix + [str(scripts / "paos.py"), "--installation-file", str(installation), "--json", "wake"]
    identity = [ref["project_id"], ref["home_id"]]

    if args.action == "bind":
        command = cli + ["bind", *identity, "--driver", driver, "--native-session-id", args.session_id]
        if args.driver_config:
            command += ["--driver-config", str(Path(args.driver_config).expanduser().resolve())]
    else:
        from paos_contact import load_native_targets
        target = (load_native_targets(Path(ref["project_root"])) or {}).get(ref["home_id"])
        if target and target["runtime"] != driver:
            raise ValueError(f"本工位已绑定 {target['runtime']}；请选择对应脚本。")
        if args.action == "prepare":
            from codex_receiver_session_start import registered_target
            thread = os.environ.get("CODEX_THREAD_ID", "")
            if not thread or not os.environ.get("CODEX_APP_TOOLS_PIPE_PATH"):
                raise ValueError("prepare 必须在本人 Codex Desktop 工具环境中执行。")
            owner, _ = registered_target(thread, descriptor)
            if Path(owner["home_path"]).resolve() != home:
                raise ValueError("当前 Codex Thread 不属于本人工位。")
            command = prefix + [str(scripts / "codex_receiver_session_start.py"), "--prepare-current"]
        elif args.action == "status":
            command = cli + ["status", *identity]
        else:
            command = cli + ["trigger", *identity, "--prompt", args.prompt]

    return subprocess.run(command, cwd=scripts if args.action == "prepare" else home, env=env).returncode


def main(driver: str, argv=None) -> int:
    parser = argparse.ArgumentParser(description=f"本工位 {driver} 唤醒入口；实现来自当前安装 Core。")
    parser.add_argument("--installation-file", default=os.environ.get("PAOS_INSTALLATION_FILE", ""),
                        help="当前安装描述绝对路径；默认 PAOS_INSTALLATION_FILE")
    commands = parser.add_subparsers(dest="action", required=True)
    bind = commands.add_parser("bind", help="登记本人真实原生会话")
    bind.add_argument("--session-id", required=True)
    bind.add_argument("--driver-config", required=driver == "opencode", help="本机私有目标配置 JSON")
    if driver == "codex":
        commands.add_parser("prepare", help="从本人 Desktop 环境准备被动接收器")
    commands.add_parser("status", help="只读本人配置与接收状态")
    wake = commands.add_parser("wake", help="向本工位已绑定会话发一次原生提醒；不保存 Mail")
    wake.add_argument("--prompt", required=True)
    args = parser.parse_args(argv)
    try:
        return execute(driver, args)
    except (OSError, ValueError, RuntimeError, KeyError, ImportError) as exc:
        print(f"wake_entry_error: {exc}", file=sys.stderr)
        return 2
