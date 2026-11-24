"""Prepare, apply and restore an exact-session Hook configuration; never set trust."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib


ROUTER = Path(__file__).with_name('paos_codex_selected_hook.py').resolve()
OLD = re.compile(r'^"([^"]+)" -X utf8 -B "([^"]+[\\/]codex_receiver_session_start\.py)"$')


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf8')


def build(original, sessions, installation, cat_url=None):
    if not sessions or any(not re.fullmatch(r'[A-Za-z0-9_-]+', s) for s in sessions) or len(set(sessions)) != len(sessions):
        raise ValueError('Provide distinct exact native session IDs')
    candidate = copy.deepcopy(original)
    hooks = candidate.get('hooks')
    if not isinstance(hooks, dict):
        raise ValueError('Expected hooks.json object')
    found = {}
    for event, groups in hooks.items():
        for group in groups:
            for handler in group['hooks']:
                command = handler.get('command', '')
                commands = '\n'.join(str(handler.get(k, '')) for k in ('command', 'commandWindows', 'command_windows'))
                if 'paos_codex_hook.py' in commands or 'paos_codex_selected_hook.py' in commands:
                    raise ValueError('Existing new adapter conflicts with selected installation')
                if 'codex_receiver_session_start.py' not in commands:
                    continue
                match = OLD.fullmatch(command)
                if (not match or handler.get('type') != 'command' or handler.get('async', False)
                        or 'commandWindows' in handler or 'command_windows' in handler):
                    raise ValueError('Original receiver command/handler differs from supported contract')
                if event not in ('SessionStart', 'UserPromptSubmit') or event in found:
                    raise ValueError('Expected exactly one original receiver in each original event')
                if event == 'SessionStart' and group.get('matcher') != '^(startup|resume)$':
                    raise ValueError('Original SessionStart matcher differs')
                if event == 'UserPromptSubmit' and group.get('matcher'):
                    raise ValueError('Original UserPromptSubmit matcher differs')
                python, script = match.groups()
                if not Path(python).is_file() or not Path(script).is_file():
                    raise ValueError('Original receiver executable/script unavailable')
                found[event] = (python, script)
    if set(found) != {'SessionStart', 'UserPromptSubmit'}:
        raise ValueError('Both original receiver handlers must exist exactly once')
    args = [sys.executable, '-X', 'utf8', '-B', str(ROUTER),
            '--installation-file', str(installation)]
    for session in sessions:
        args.extend(['--session', session])
    if cat_url:
        args.extend(['--cat-url', cat_url])
    for event in ('SessionStart', 'UserPromptSubmit', 'Stop'):
        handler = dict(type='command', command=subprocess.list2cmdline(args), timeout=30)
        if event != 'Stop':
            handler['additionalContextLimit'] = 0
        group = {'hooks': [handler]}
        if event == 'SessionStart':
            group['matcher'] = '^(startup|resume|compact)$'
        hooks.setdefault(event, []).append(group)
    return candidate


def check_inline_conflict(hooks_file):
    toml = hooks_file.with_name('config.toml')
    if toml.exists():
        inline = tomllib.loads(toml.read_text(encoding='utf8')).get('hooks', {})
        inline.pop('state', None)  # Trust records are not executable hook registrations.
        if any(name in json.dumps(inline) for name in
               ('codex_receiver_session_start.py', 'paos_codex_hook.py', 'paos_codex_selected_hook.py')):
            raise ValueError('Duplicate PAOE hooks in sibling config.toml; resolve source conflict first')


def prepare(hooks_file, packet, sessions, installation, cat_url=None):
    hooks_file, packet = Path(hooks_file).resolve(), Path(packet).resolve()
    installation = Path(installation).resolve()
    if not installation.is_file():
        raise ValueError('Explicit selected installation is missing')
    check_inline_conflict(hooks_file)
    original = hooks_file.read_bytes()
    candidate = build(json.loads(original), sessions, installation, cat_url)
    packet.mkdir(parents=True, exist_ok=False)
    (packet / 'original.json').write_bytes(original)
    (packet / 'candidate.json').write_bytes(encode(candidate))
    (packet / 'plan.json').write_bytes(encode(dict(schema='paoe-codex-selected-install/v1',
        hooks_file=str(hooks_file), sessions=sessions, installation_file=str(installation),
        cat_url=cat_url, router=str(ROUTER))))
    return {'ok': True, 'packet': str(packet), 'action': 'prepared', 'trust_review_required': True}


def replace_checked(path, expected, replacement):
    if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
        raise ValueError('Hook configuration conflict; current bytes differ, no write')
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(replacement)
        if path.read_bytes() != expected:
            raise ValueError('Hook configuration changed before replacement, no write')
        os.replace(temporary, path)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def apply(packet, *, restore=False):
    packet = Path(packet)
    plan = json.loads((packet / 'plan.json').read_bytes())
    if plan.get('schema') != 'paoe-codex-selected-install/v1':
        raise ValueError('Unknown installation packet')
    original, candidate = (packet / 'original.json').read_bytes(), (packet / 'candidate.json').read_bytes()
    # Ensure the reviewable candidate still matches the recorded selection and originals.
    if not restore:
        check_inline_conflict(Path(plan['hooks_file']))
        if not Path(plan['installation_file']).is_file():
            raise ValueError('Selected installation disappeared')
        rebuilt = build(json.loads(original), plan['sessions'], plan['installation_file'], plan['cat_url'])
        if json.loads(candidate) != rebuilt or plan['router'] != str(ROUTER):
            raise ValueError('Candidate or executable location changed; prepare a new packet')
    expected, replacement = (candidate, original) if restore else (original, candidate)
    replace_checked(Path(plan['hooks_file']), expected, replacement)
    return {'ok': True, 'action': 'restored' if restore else 'applied',
            'hooks_file': plan['hooks_file'], 'trust_review_required': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    make = sub.add_parser('prepare')
    make.add_argument('--hooks-file', required=True)
    make.add_argument('--packet', required=True)
    make.add_argument('--session', action='append', required=True)
    make.add_argument('--installation-file', required=True)
    make.add_argument('--cat-url')
    for action in ('apply', 'restore'):
        sub.add_parser(action).add_argument('--packet', required=True)
    args = parser.parse_args()
    try:
        result = (prepare(args.hooks_file, args.packet, args.session, args.installation_file, args.cat_url)
                  if args.action == 'prepare' else apply(args.packet, restore=args.action == 'restore'))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {'ok': False, 'error': str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
