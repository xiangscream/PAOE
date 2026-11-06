#!/usr/bin/env python3
"""Build a deterministic System archive from committed Git objects only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent


def git(*args: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(ROOT), *args], stderr=subprocess.PIPE)


def encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def validate_path(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name:
        raise ValueError(f'unsafe archive path: {name}')
    if any(p in {'.git', '.backups', '.obsidian', '__pycache__', 'node_modules', 'private-data'} for p in path.parts):
        raise ValueError(f'private/generated path is tracked: {name}')
    if name.startswith(('Core/config/local/', 'Core/data/', 'rooter/')) and name != 'rooter/README.md':
        raise ValueError(f'machine state is tracked: {name}')
    if path.name in {'.env', 'native-targets.json', 'runtime.json', 'auth.json', 'id_rsa'}:
        raise ValueError(f'private file is tracked: {name}')


def category(name: str) -> str:
    if name.startswith('Core/'):
        return 'core-source'
    if name.startswith('Project-Template/'):
        return 'project-template'
    if name == 'rooter/README.md':
        return 'rooter-public'
    if name == 'PROJECTS.md':
        return 'neutral-project-entry'
    return 'system-source'


def collect(ref: str):
    if git('status', '--porcelain=v1', '--untracked-files=all').strip():
        raise ValueError('release source checkout is dirty; preserve edits and commit before building')
    commit = git('rev-parse', '--verify', ref + '^{commit}').decode().strip()
    payload = {}
    modes = {}
    for row in git('ls-tree', '-r', '-z', commit).split(b'\0'):
        if not row:
            continue
        info, raw_name = row.split(b'\t', 1)
        mode, kind, oid = info.decode('ascii').split()
        name = raw_name.decode('utf-8')
        validate_path(name)
        if kind != 'blob' or mode not in {'100644', '100755'}:
            raise ValueError(f'ordinary files required; no submodule or symlink: {name}')
        payload[name] = git('cat-file', 'blob', oid)
        modes[name] = int(mode, 8)
    required = {'VERSION', 'SOURCE.lock.json', 'README.md', 'UPGRADE.md', 'HOME.md',
                'SYSTEM.md', 'PROJECTS.md', 'RESOURCES.md', 'MAINTENANCE.md',
                'rooter/README.md', 'Core/portable.py', 'Guide/README.md',
                'Project-Template/AGENTS.md', 'Project-Template/INDEX.md',
                'Project-Template/TEAM.md', 'Project-Template/Workstations/_workstation/ENTRY.md',
                'Project-Template/Workstations/_workstation/TODO.md'}
    if required - payload.keys():
        raise ValueError('missing release source: ' + ', '.join(sorted(required - payload.keys())))
    version = payload['VERSION'].decode('ascii').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', version):
        raise ValueError('invalid System VERSION')
    lock = json.loads(payload['SOURCE.lock.json'])
    if lock.get('schema') != 'paoe-system-source/v1':
        raise ValueError('invalid source lock schema')
    actual_core_tree = git('rev-parse', commit + ':Core').decode().strip()
    if actual_core_tree != lock['core_tree']:
        raise ValueError('Core tree differs from the frozen source lock')
    secret_patterns = [rb'sk-(?:proj|svcacct)-[A-Za-z0-9_-]{32,}', rb'gh[pousr]_[A-Za-z0-9]{30,}',
                       rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']
    for name, data in payload.items():
        if any(re.search(pattern, data) for pattern in secret_patterns):
            raise ValueError(f'credential-shaped content requires review: {name}')
        if not name.startswith('Core/') and ((b'C:/Users/' + b'ASUS') in data or (b'D:/' + b'PAOS-Projects') in data):
            raise ValueError(f'machine path in public source: {name}')
    payload['BUILD.json'] = encoded({'schema': 'paoe-system-build/v1', 'version': version,
        'system_commit': commit, 'core_commit': lock['core_commit'], 'core_tree': actual_core_tree})
    modes['BUILD.json'] = 0o100644
    manifest = {'schema': 'paoe-system-files/v1', 'version': version, 'system_commit': commit,
        'files': [{'path': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                   'category': category(name), 'mode': modes[name]}
                  for name, data in sorted(payload.items())]}
    payload['FILES.json'] = encoded(manifest)
    modes['FILES.json'] = 0o100644
    return version, payload, modes, manifest


def build(ref: str, output: Path) -> dict:
    version, payload, modes, manifest = collect(ref)
    output = output.resolve(); output.mkdir(parents=True, exist_ok=True)
    target = output / f'PAOE-System-{version}.zip'
    with tempfile.NamedTemporaryFile(dir=output, prefix='.system-release-', suffix='.tmp', delete=False) as stream:
        staged = Path(stream.name)
    try:
        # Stored ZIP avoids compressor-version differences; all other metadata is fixed.
        with zipfile.ZipFile(staged, 'w', compression=zipfile.ZIP_STORED) as archive:
            for name, data in sorted(payload.items()):
                info = zipfile.ZipInfo(f'PAOE-System-{version}/' + name, (1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = modes[name] << 16
                info.compress_type = zipfile.ZIP_STORED
                archive.writestr(info, data)
        digest = hashlib.sha256(staged.read_bytes()).hexdigest()
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError('same version already has different archive bytes; do not overwrite a release')
        if not target.exists():
            staged.replace(target)
        (output / 'FILES.json').write_bytes(payload['FILES.json'])
        (output / (target.name + '.sha256')).write_text(digest + '  ' + target.name + '\n', encoding='ascii')
        return {'archive': str(target), 'sha256': digest, 'files': len(manifest['files']),
                'system_commit': manifest['system_commit'], 'version': version}
    finally:
        staged.unlink(missing_ok=True)


def verify(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or archive.testzip() is not None:
            raise ValueError('duplicate or corrupt archive member')
        roots = {name.split('/', 1)[0] for name in names}
        if len(roots) != 1:
            raise ValueError('archive must contain one System root')
        prefix = next(iter(roots)) + '/'
        manifest = json.loads(archive.read(prefix + 'FILES.json'))
        if manifest.get('schema') != 'paoe-system-files/v1':
            raise ValueError('invalid file manifest')
        expected = {prefix + item['path'] for item in manifest['files']} | {prefix + 'FILES.json'}
        if set(names) != expected:
            raise ValueError('archive file set differs from manifest')
        for item in manifest['files']:
            validate_path(item['path'])
            data = archive.read(prefix + item['path'])
            if len(data) != item['size'] or hashlib.sha256(data).hexdigest() != item['sha256']:
                raise ValueError('file checksum mismatch: ' + item['path'])
        build_info = json.loads(archive.read(prefix + 'BUILD.json'))
        if build_info['system_commit'] != manifest['system_commit']:
            raise ValueError('build identity differs from manifest')
    return {'ok': True, 'files': len(manifest['files']), 'version': manifest['version'],
            'system_commit': manifest['system_commit'], 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('build'); create.add_argument('--ref', required=True)
    create.add_argument('--output', type=Path, required=True)
    check = commands.add_parser('verify'); check.add_argument('archive', type=Path)
    args = parser.parse_args(argv)
    try:
        result = build(args.ref, args.output) if args.command == 'build' else verify(args.archive)
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        print(f'release_error: {exc}', file=sys.stderr); return 2


if __name__ == '__main__':
    raise SystemExit(main())
