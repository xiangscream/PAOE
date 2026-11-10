"""Render a disposable Markdown overview from registered Homes and TEAM originals.

No runtime probes, Home writes, native launches, or secondary member registry.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import unquote

from paos_contact import _team_role_summaries
from paos_installation import effective_data_root, load_installation_descriptor
from paos_registry import ProjectRegistry
from paos_workstation import posix_windows_drive_locator

MARKER = '<!-- paoe:team-overview:generated -->'


def _find_matching(text: str, start: int, opener: str, closer: str) -> int:
    """Find a balanced closing delimiter, ignoring escaped characters."""
    depth = 0
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
        elif char == '\\':
            escaped = True
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return index
    return -1


def _find_link_end(text: str, start: int) -> int:
    """Find the closing parenthesis of an inline link or image destination."""
    depth = 1
    in_angle = False
    for index in range(start, len(text)):
        char = text[index]
        if in_angle:
            if char == '>':
                in_angle = False
        elif char == '<':
            in_angle = True
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0:
                return index
    return -1


def _is_absolute_or_remote(destination: str) -> bool:
    if destination.startswith(('#', '?', '/', '\\')):
        return True
    if re.match(r'^[A-Za-z]:[\\/]', destination):
        return True
    return bool(re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', destination))


def _relocate_source_links(value: str, source: Path) -> str:
    """Make relative Markdown destinations resolve from the source file.

    TEAM role and Harness cells are copied into a generated overview in another
    directory.  Relative links in those cells must therefore be made
    source-relative before rendering.  Labels, anchors, titles, absolute paths,
    remote URLs and URI schemes are retained.
    """
    if not value or '](' not in value:
        return value
    base = source.resolve().parent
    out: list[str] = []
    index = 0
    while index < len(value):
        if value[index] != '[' or (index and value[index - 1] == '!'):
            out.append(value[index])
            index += 1
            continue
        label_end = _find_matching(value, index, '[', ']')
        if label_end < 0 or label_end + 1 >= len(value) or value[label_end + 1] != '(':
            out.append(value[index])
            index += 1
            continue
        link_end = _find_link_end(value, label_end + 2)
        if link_end < 0:
            out.append(value[index])
            index += 1
            continue
        raw = value[label_end + 2:link_end].strip()
        if raw.startswith('<'):
            close = raw.find('>')
            if close < 0:
                out.append(value[index:link_end + 1])
                index = link_end + 1
                continue
            destination = raw[1:close]
            title = raw[close + 1:]
        else:
            match = re.match(r'(\S+)(.*)$', raw, re.S)
            if not match:
                out.append(value[index:link_end + 1])
                index = link_end + 1
                continue
            destination = match.group(1)
            title = match.group(2)
        if not destination or _is_absolute_or_remote(destination):
            out.append(value[index:link_end + 1])
            index = link_end + 1
            continue
        filename, separator, fragment = destination.partition('#')
        try:
            target = (base / unquote(filename)).resolve().as_uri()
        except (OSError, ValueError):
            out.append(value[index:link_end + 1])
            index = link_end + 1
            continue
        if separator:
            target += '#' + fragment
        out.append(f'{value[index:label_end + 1]}(<{target}>{title})')
        index = link_end + 1
    return ''.join(out)


def _powershell(*args: str) -> str:
    return '& ' + ' '.join("'" + str(arg).replace("'", "''") + "'" for arg in args)


def _team_harness_summaries(team: Path, registered_ids: set[str]) -> dict[str, str]:
    """Read actual Harness values from the current TEAM member sections."""
    try:
        lines = team.read_text(encoding='utf-8-sig').splitlines()
    except (OSError, UnicodeError):
        return {}
    harnesses: dict[str, str] = {}
    in_current = False
    current: str | None = None
    for line in lines:
        if line.startswith('## '):
            in_current = line.strip() == '## 当前成员'
            current = None
        elif in_current and line.startswith('### '):
            candidate = line[4:].strip()
            current = candidate if candidate in registered_ids else None
        elif current:
            match = re.match(r'^\s*-\s*Harness\s*[：:]\s*(.+)$', line)
            if match:
                harnesses[current] = match.group(1).strip()
    return harnesses


def render_overview(installation_file: Path, output: Path) -> str:
    installation_file, output = installation_file.resolve(), output.resolve()
    installation = load_installation_descriptor(installation_file)
    if not installation.get('configured'):
        raise ValueError(f'安装描述未配置：{installation_file}')
    registry = ProjectRegistry(installation_file)
    fingerprints: list[str] = []

    def read(path: Path) -> str:
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            fingerprints.append(f'{path}:missing')
            return ''
        fingerprints.append(f'{path}:{hashlib.sha256(data).hexdigest()}')
        return data.decode('utf-8-sig')

    def link(label: str, path: Path, anchor: str = '') -> str:
        suffix = '' if path.is_file() else '（缺失）'
        return f'[{label}](<{path.resolve().as_uri()}{anchor}>){suffix}'

    def cell(value: str) -> str:
        return ' '.join(value.split()).replace('|', r'\|')

    read(installation_file)
    projects = []
    registry_dir = effective_data_root(installation) / 'project-registry/projects'
    for path in sorted(registry_dir.glob('*.json')):
        read(path)
        record = registry.read_record(path.stem)
        root = Path(posix_windows_drive_locator(record['root_path'])).expanduser()
        team = root / 'TEAM.md'
        read(team)
        home_ids = set(record['homes'])
        projects.append((record, root, team, _team_role_summaries(root, home_ids),
                         _team_harness_summaries(team, home_ids)))

    members: list[tuple[str, Path]] = []

    def row(home_id: str, home: Path, role: str, harness: str, source: str,
            source_path: Path) -> str:
        entry = home / 'ENTRY.md'
        read(entry)
        contact = home / 'contact.py'
        # Only file presence is observed; configuration is not an online check.
        fingerprints.append(f'{contact}:exists={contact.is_file()}')
        if contact.is_file():
            members.append((home_id, contact))
            wake = f'[命令](#{home_id})'
        else:
            wake = '联系入口未配置，状态和接续见ENTRY'
        role_text = _relocate_source_links(role, source_path)
        harness_cell = (cell(_relocate_source_links(harness, source_path))
                        if harness else f'未注明，读 {source}')
        return (f'| {home_id} | {cell(role_text)} | {harness_cell} | '
                f'{link("ENTRY", entry)} · {link("TODO", home / "TODO.md")} | {wake} |')

    project_table = ['| Agent | 职责 / 专长 | Harness（TEAM） | 工位 | 唤醒 |',
                     '| --- | --- | --- | --- | --- |']
    lines = ['# 项目与 Agent · TEAM 聚合', '', MARKER, '',
             '<!-- paoe:human-intro:start -->',
             '> 按项目找成员与唤醒入口。职责维护在项目 TEAM；本页由原件生成。',
             '<!-- paoe:human-intro:end -->', '', '<!-- paoe:agent-reference -->', '']
    if not projects:
        lines += ['当前登记范围内没有 Project。', '']
    for record, root, team, roles, harnesses in projects:
        project_id = record['id']
        lines += [f'## 项目 {project_id} · {cell(root.name)}', '',
                  f'原件：{link("TEAM", team)} · {link("INDEX", root / "INDEX.md")} · '
                  f'{link("Registry", registry_dir / (project_id + ".json"))}', '']
        if not team.is_file():
            lines += ['TEAM 原件缺失；仍列出登记成员，不猜职责或 Harness。', '']
        lines += project_table
        for home_id in record['homes']:
            lines.append(row(home_id, root / 'Workstations' / home_id,
                             roles.get(home_id) or '未识别，打开 TEAM 原文',
                             harnesses.get(home_id) or '', 'TEAM', team))
        lines.append('')

    raw_rooter = str(installation.get('rooter_home') or '')
    if raw_rooter:
        home = Path(posix_windows_drive_locator(raw_rooter)).expanduser()
        rooter_harness = re.search(r'^- Harness[：:]\s*(.+)$',
                                   read(home / 'ENTRY.md'), re.M)
        rooter_table = ['| Agent | 职责 / 专长 | Harness（ENTRY） | 工位 | 唤醒 |',
                        '| --- | --- | --- | --- | --- |']
        lines += ['## 安装级支持', '', *rooter_table,
                  row('rooter-001', home, '职责见本人 ENTRY；不属于 Project',
                      rooter_harness.group(1) if rooter_harness else '', 'ENTRY',
                      home / 'ENTRY.md'), '']

    lines += ['## 外部唤醒', '',
              '适用于获准在本机执行命令的 Agent。下列命令只提醒原会话；持久留信按 OPS 的正式 Mail 入口。',
              '将消息替换为具体请求和原件绝对路径。`accepted=true` 只表示提醒受理；当前状态用同一脚本的 `status` 核对。', '']
    for home_id, contact in members:
        lines += [f'### {home_id}', '', '```powershell',
                  _powershell(sys.executable, '-X', 'utf8', '-B', str(contact),
                              'wake', '--message', '请处理：具体请求；相关原件：绝对路径。'),
                  '```', '']

    source = Path(posix_windows_drive_locator(installation['source_root']))
    command = _powershell(sys.executable, '-X', 'utf8', '-B',
                          str(source / 'scripts/paos_team_overview.py'),
                          '--installation-file', str(installation_file), '--output', str(output))
    lines += ['## 更新与检查', '',
              '本页是可重建的汇总，不手改成员信息。修改登记、TEAM 或 ENTRY 后刷新；需要准确事实时直接读取上方原件。',
              '本页不探测在线、不保存任务进度，也不证明已消费。', '',
              '```powershell', command + " '--write'", command + " '--check'", '```', '']
    stamp = hashlib.sha256('\n'.join(fingerprints).encode('utf-8')).hexdigest()
    lines += [f'<!-- sources-sha256: {stamp} -->', '']
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation-file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--write', action='store_true', help='Replace the generated overview only')
    mode.add_argument('--check', action='store_true', help='Exit 1 if missing or stale; never write')
    args = parser.parse_args(argv)
    try:
        content = render_overview(args.installation_file, args.output)
        old = args.output.read_text(encoding='utf-8-sig') if args.output.exists() else None
        if args.check:
            if old != content:
                print(f'过期或缺失：{args.output}；按同一命令加 --write 重建。')
                return 1
            print(f'一致：{args.output}')
        elif args.write:
            if old == content:
                print(f'无变化：{args.output}')
                return 0
            if old is not None and MARKER not in old:
                raise ValueError('输出不是已标记的派生页；先保存并迁出人工原件，再建立聚合页。')
            if args.output.is_symlink():
                raise ValueError('拒绝替换符号链接输出。')
            with tempfile.NamedTemporaryFile(dir=args.output.parent, prefix='.team-',
                                             suffix='.tmp', delete=False) as stream:
                stage = Path(stream.name)
                stream.write(content.encode('utf-8'))
            try:
                # Detect ordinary concurrent edits before publishing.
                latest = args.output.read_text(encoding='utf-8-sig') if args.output.exists() else None
                if latest != old:
                    raise ValueError('输出已被其他写者修改；未覆盖，请重读。')
                os.replace(stage, args.output)
            finally:
                stage.unlink(missing_ok=True)
            print(f'已更新：{args.output}')
        else:
            print(content, end='')
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'TEAM 聚合失败：{exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
