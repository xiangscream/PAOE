"""Route an exact native session to the reviewed adapter, preserving other receivers."""
import argparse
import json
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', action='append', required=True)
    parser.add_argument('--installation-file')
    parser.add_argument('--cat-url')
    args = parser.parse_args()
    raw = sys.stdin.buffer.read()
    try:
        event = json.loads(raw)
        if not isinstance(event, dict) or not isinstance(event.get('session_id'), str) or not event['session_id']:
            raise ValueError('Expected native session_id')
        selected = event['session_id'] in args.session
        if not selected:
            response = {}  # No installation read, prepare, context read or Stop action.
        else:
            if not args.installation_file:
                raise ValueError('Selected hook requires explicit installation')
            from pathlib import Path
            command = [sys.executable, '-X', 'utf8', '-B',
                       str(Path(__file__).with_name('paos_codex_hook.py')),
                       '--installation-file', args.installation_file, '--reuse-existing-prepare']
            if args.cat_url:
                command.extend(['--cat-url', args.cat_url])
            result = subprocess.run(command, input=raw, capture_output=True, timeout=25)
            sys.stdout.buffer.write(result.stdout)
            sys.stderr.buffer.write(result.stderr)
            return result.returncode
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        response = {'continue': False, 'stopReason': f'PAOE selected Hook: {exc}'}
    sys.stdout.buffer.write((json.dumps(response, ensure_ascii=False) + '\n').encode('utf8'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
