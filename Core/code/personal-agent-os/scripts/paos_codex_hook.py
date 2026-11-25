"""Translate registered Codex lifecycle events to PAOE's shared context actions."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from codex_receiver_session_start import registered_target, prepare_current, observe_hook_entry
from paos_installation import load_installation_descriptor, resolve_installation_path, InstallationProblem
from paos_attention_service import AttentionServiceProblem
from paos_home import HomeProblem
from paos_registry import RegistryProblem
from paos_workstation import WorkstationProblem, posix_windows_drive_locator
from wakeup_native.codex_receiver import ReceiverError
from runtime_injection import InjectionError


SCRIPTS = Path(__file__).resolve().parent


class HookProblem(ValueError):
    pass


def call_context(installation, args):
    result = subprocess.run(
        [sys.executable, '-X', 'utf8', str(SCRIPTS / 'paos.py'),
         '--installation-file', str(installation), '--json', 'context', *args],
        stdin=subprocess.DEVNULL, capture_output=True, encoding='utf-8', timeout=8,
        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, check=False,
    )
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise HookProblem('共用动作返回格式无效')
    if result.returncode or value.get('ok') is not True:
        missing = value.get('missing', [])
        raise HookProblem('共用动作未完成：' + json.dumps(missing or value.get('error', 'unknown'), ensure_ascii=False))
    return value


def run_hook(event, installation, cat_url=None):
    name = event.get('hook_event_name')
    reason = event.get('source') if name == 'SessionStart' else 'request'
    if name not in {'SessionStart', 'UserPromptSubmit', 'Stop'}:
        return {}
    if name == 'SessionStart' and reason not in {'startup', 'resume', 'compact'}:
        return {}
    session = event.get('session_id')
    if not isinstance(session, str) or not session:
        raise HookProblem('宿主事件缺少 session_id')
    owner = os.environ.get('CODEX_THREAD_ID')
    if owner and owner != session:
        raise HookProblem('宿主事件与当前原生会话不符')
    descriptor = load_installation_descriptor(installation)
    try:
        home, target = registered_target(session, descriptor)
    except ValueError as exc:
        if str(exc) == 'contact_thread_not_registered':
            return {}  # The global hook also sees conversations outside PAOE.
        raise
    stop = target.get('stop_file')
    if not isinstance(stop, str) or not stop:
        raise HookProblem('本人 Contact 缺少 STOP 定位')
    if Path(posix_windows_drive_locator(stop)).exists():
        return {'continue': False, 'stopReason': '本人 STOP 存在，停止自动接续。'}
    if name == 'Stop':
        turn = event.get('turn_id')
        reentry = event.get('stop_hook_active')
        if not isinstance(turn, str) or not turn or type(reentry) is not bool:
            raise HookProblem('Stop 缺少原生 turn_id 或 stop_hook_active')
        key = f'codex:{session}:{turn}'
        args = ['stop', home['home_id'], '--event', key]
        if reentry:
            args.append('--reentry')
        if cat_url:
            args.extend(['--cat-url', cat_url])
        result = call_context(installation, args)
        if result.get('schema') != 'paoe-context-stop/v1' or result.get('event') != key:
            raise HookProblem('Stop 回执与当前原生回合不符')
        if result.get('action') == 'stop':
            return {}
        if result.get('action') != 'continue' or not isinstance(result.get('next_action'), str) or not result['next_action'].strip():
            raise HookProblem('Stop 回执缺少有效动作')
        if reentry:
            raise HookProblem('共用 Stop 在重入时仍要求继续')
        return {'decision': 'block', 'reason': result['next_action']}

    # Reading originals works even when a local hook lacks the Desktop pipe.
    # Receiver preparation still requires the original Desktop environment.
    observe_hook_entry(event, installation_path=installation, entrypoint='context')
    message = prepare_current(event=event, installation_path=installation, expected_home=home)
    args = ['read', home['home_id'], '--reason', reason]
    if cat_url:
        args.extend(['--cat-url', cat_url])
    result = call_context(installation, args)
    if result.get('schema') != 'paoe-context/v1' or result.get('home_id') != home['home_id'] or result.get('reason') != reason:
        raise HookProblem('上下文回执与当前工位或事件不符')
    docs = result.get('documents')
    if result.get('missing') != [] or not isinstance(docs, list) or not docs:
        raise HookProblem('共用读取没有给出完整必读原文')
    if any(not isinstance(d, dict) or any(not isinstance(d.get(k), str) or not d[k].strip()
           for k in ('kind', 'path', 'body', 'version')) for d in docs):
        raise HookProblem('必读原件内容或版本不完整')
    text = '\n\n'.join(f"[{d['kind']}] {d['path']}\n{d['body']}" for d in docs)
    if os.name == 'nt' and message == 'receiver_prepare_skipped: original_desktop_environment_missing':
        command = ('attention rooter-show --resume' if home['home_kind'] == 'rooter'
                   else f"orient {home['project_id']} {home['home_id']} --resume")
        text += (
            '\n\n[PAOE 接收器] Hook 缺少本人 Desktop 工具环境，尚未检查接收器。'
            '请在当前原会话的终端，用本人 ENTRY 的 CLI 前缀运行一次 '
            f'`{command}`，再继续处理当前输入。同一回合只运行一次。'
        )
    return {'systemMessage': message, 'hookSpecificOutput': {
        'hookEventName': name, 'additionalContext': '[PAOE 本次必读原文]\n\n' + text,
    }}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation-file')
    parser.add_argument('--cat-url', help='Installation CAT endpoint for context reads and Stop presence')
    args = parser.parse_args()
    event = {}
    try:
        event = json.load(sys.stdin.buffer)
        if not isinstance(event, dict):
            raise HookProblem('宿主事件必须为 JSON 对象')
        installation = resolve_installation_path(args.installation_file)
        response = run_hook(event, installation, args.cat_url)
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired, InstallationProblem,
            AttentionServiceProblem, HomeProblem, RegistryProblem, WorkstationProblem, ReceiverError,
            InjectionError) as exc:
        # Return the native explicit stop shape, not an exception exit that the
        # host might treat as a failed non-blocking hook. Never request retries.
        message = f'PAOE Hook 未完成：{exc}'
        response = {'continue': False, 'stopReason': message, 'systemMessage': message}
    sys.stdout.buffer.write((json.dumps(response, ensure_ascii=False) + '\n').encode('utf-8'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
