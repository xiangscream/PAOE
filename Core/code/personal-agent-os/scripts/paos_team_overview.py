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

from paos_agent_numbers import NumbersProblem, load_numbers, resolve_numbers_path
from paos_contact import _team_heading_home, _team_role_summaries, team_member_statuses
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


def _heading_anchor(title: str) -> str:
    label = re.sub(r'\[([^]]+)\]\([^)]+\)', r'\1', title)
    return re.sub(r'[^\w\- ]', '', label.lower()).replace(' ', '-')


def _team_harness_summaries(team: Path, registered_ids: set[str],
                            numbers_map: dict[str, str] | None = None) -> dict[str, str]:
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
            current = _team_heading_home(line[4:].strip(), registered_ids, numbers_map)
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
    try:
        numbers_path = resolve_numbers_path(None, installation_file, installation)
        numbers_map = load_numbers(numbers_path)
    except NumbersProblem as exc:
        raise ValueError(f'员工号登记不可用，无法生成准确 PROJECTS：{exc}') from exc
    staff_numbers = set(numbers_map.values())
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

    def row(home_id: str, home: Path, role: str, harness: str, source: Path,
            status: str = '') -> str:
        entry = home / 'ENTRY.md'
        entry_text = read(entry)
        staff = home_id if home_id in staff_numbers else numbers_map.get(home_id)
        if not staff:
            raise ValueError(
                f'员工号登记缺少 {home_id} 的映射；先补安装 AGENT-NUMBERS.json，不由 Home 尾号猜。')
        if source == entry:
            match = re.search(r'^- Harness\s*[：:]\s*([^\n；;]+)', entry_text, re.M)
            harness = match.group(1).strip() if match else ''
        role_text = cell(_relocate_source_links(role, source))
        runtime = (cell(_relocate_source_links(harness.rstrip('。'), source))
                   if harness else f'未注明，读 {source.stem}')
        if status.startswith('暂停'):
            runtime += ' · 暂停'
        if ('人工联系' in re.split(r'\s*[，,；;。]\s*', status)
                or re.search(r'^\s*-\s*(?:你的)?人工联系入口\s*[：:]', entry_text, re.M)):
            runtime += ' · 人工联系'
        return f'| {link(staff, entry)} | {role_text} | {runtime} | {link("待办", home / "TODO.md")} |'

    read(installation_file)
    read(numbers_path)
    navigation = ['[联系方法](#外部唤醒)']
    project_table = ['| 员工 | 职责 | 运行端 | 当前工作 |', '| --- | --- | --- | --- |']
    sections: list[str] = []
    headings = {'项目与同事', '安装级支持', '外部唤醒', '更新与检查'}
    registry_dir = effective_data_root(installation) / 'project-registry/projects'
    for path in sorted(registry_dir.glob('*.json')):
        read(path)
        record = registry.read_record(path.stem)
        root = Path(posix_windows_drive_locator(record['root_path'])).expanduser()
        team = root / 'TEAM.md'
        read(team)
        index = root / 'INDEX.md'
        heading = re.search(r'^# +(.+?) *#* *$', read(index), re.M)
        title = heading.group(1).strip() if heading else root.name
        anchor = _heading_anchor(title)
        if not anchor or anchor in headings:
            title = f'{title}（{record["id"]}）'
            anchor = _heading_anchor(title)
        headings.add(anchor)
        navigation.append(f'[{title}](#{anchor})')
        sections += [f'## {title}', '',
                     f'项目 {record["id"]}　{link("项目首页", index)} · {link("团队分工", team)}', '']
        if not team.is_file():
            sections += ['TEAM 原件缺失。已登记员工的工位入口仍可使用。', '']
        sections += project_table
        home_ids = set(record['homes'])
        roles = _team_role_summaries(root, home_ids, numbers_map)
        harnesses = _team_harness_summaries(team, home_ids, numbers_map)
        statuses = team_member_statuses(str(team), record['homes'], numbers_map)
        for home_id in record['homes']:
            sections.append(row(home_id, root / 'Workstations' / home_id,
                                roles.get(home_id) or '未识别，打开 TEAM 原文',
                                harnesses.get(home_id, ''), team, statuses.get(home_id, '')))
        sections.append('')
    if not sections:
        sections += ['当前登记范围内没有 Project。', '']

    raw_rooter = str(installation.get('rooter_home') or '')
    rooter_help = ''
    if raw_rooter:
        home = Path(posix_windows_drive_locator(raw_rooter)).expanduser()
        navigation.append('[Rooter](#安装级支持)')
        sections += ['## 安装级支持', '', *project_table,
                     row('rooter-001', home, '安装、更新与恢复，详见本人 ENTRY。', '', home / 'ENTRY.md'), '']
        rooter_help = f'联系安装级 Rooter 时，项目参数填 `rooter`，员工号填 `{numbers_map["rooter-001"]}`。'

    lines = ['# 项目与同事', '', MARKER, '',
             '<!-- paoe:human-intro:start -->',
             '选项目找负责人。点员工号进入工位，点「待办」查看本人当前工作。完整分工由各项目的 TEAM 维护。',
             '<!-- paoe:human-intro:end -->', '', ' · '.join(navigation), '',
             '<!-- paoe:agent-reference -->', '', *sections]
    lines += ['## 外部唤醒', '',
              '已有信件或文件要对方接着处理时，用接收方的项目号和员工号提醒一次。'
              '在本机 CLI 中将尖括号里的内容换成实际值。' + rooter_help, '',
              '```text',
              'paos wake trigger <接收方项目号> <员工号> --prompt "请读取 <原消息编号或文件位置>，接续 <具体工作>。"',
              '```', '',
              '交新任务时用 `agent send --remind` 留信并提醒，发送上下文取本次工作的项目。'
              '名册中标为「人工联系」的成员，在其原会话提示读信。标为「暂停」的成员沿原安排接续。', '',
              '[成员留信](Guide/ops-entry.md#联系同事与-rooter) · '
              '[外部协作者留信](Guide/ops-entry.md#外部-agent-临时协作) · '
              '[本机 CLI 入口](Guide/ops-entry.md#操作与参考)', '']

    source = Path(posix_windows_drive_locator(installation['source_root']))
    command = _powershell(sys.executable, '-X', 'utf8', '-B',
                          str(source / 'scripts/paos_team_overview.py'),
                          '--installation-file', str(installation_file), '--output', str(output))
    lines += ['## 更新与检查', '',
              '成员信息由登记、TEAM 和 ENTRY 提供。原件更新后，用下方命令刷新或检查。',
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
    except (OSError, ValueError, RuntimeError, NumbersProblem) as exc:
        print(f'TEAM 聚合失败：{exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
