"""Read-only checks for an installed System and its Project mother.

The System supplies prose, paths and retired-locator arguments. Core supplies
link/anchor checking, template expansion and existing schema checks. No network,
registry repair, Home rewrite, polling or dependency database is involved.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import unquote

from paos_agents_common import source_block, registered_targets, inspect_target
from paos_installation import load_installation_descriptor
from paos_registry import ProjectRegistry, RegistryProblem
from paos_team_overview import render_overview
from paos_todo import parse_todo
from paos_workstation import render_fixed_entry, posix_windows_drive_locator, WorkstationProblem


def prose(text: str) -> str:
    """Keep line numbers while excluding fenced command/code examples."""
    result, fenced = [], False
    for line in text.splitlines():
        if re.match(r'^\s*(```|~~~)', line):
            fenced = not fenced
            result.append('')
        else:
            result.append('' if fenced else line)
    return '\n'.join(result)


def anchors(text: str) -> set[str]:
    result, seen = set(), Counter()
    for heading in re.findall(r'^#{1,6}\s+(.+?)\s*#*$', prose(text), re.M):
        heading = re.sub(r'\[([^]]+)\]\([^)]+\)', r'\1', heading)
        slug = re.sub(r'[^\w\- ]', '', heading.lower()).replace(' ', '-')
        number = seen[slug]; seen[slug] += 1
        result.add(slug + (f'-{number}' if number else ''))
    result.update(re.findall(r'\b(?:id|name)=["\']([^"\']+)["\']', text))
    return result


def local_links(path: Path, text: str):
    for n, line in enumerate(prose(text).splitlines(), 1):
        # Markdown inline links; angle destinations preserve spaces.
        for raw in re.findall(r'\]\((<[^>\n]+>|[^)\n]+)\)', line):
            if '{{' in raw or any(x in raw for x in ('<home-', '<project-', '<本人', '<真实')):
                continue
            dest = raw.strip('<>')
            if re.match(r'^(https?:|mailto:|obsidian:)', dest):
                continue
            filename, _, fragment = dest.partition('#')
            if filename.startswith('file:///'):
                filename = filename[8:]
            filename, fragment = unquote(filename), unquote(fragment)
            if '<' in filename or '>' in filename:
                continue
            disk = Path(posix_windows_drive_locator(filename)).expanduser()
            target = ((disk if disk.is_absolute() else path.parent / disk).resolve()
                      if filename else path.resolve())
            yield n, target, fragment


def inspect_markdown(path: Path, retired=()):
    errors, links = [], []
    try:
        text = path.read_text('utf-8-sig')
    except (OSError, UnicodeError) as exc:
        return [f'{path}: 不可读 ({exc})'], links
    for n, line in enumerate(prose(text).splitlines(), 1):
        for locator in retired:
            if locator in line:
                errors.append(f'{path}:{n}: 退役定位 {locator}')
    for n, target, fragment in local_links(path, text):
        links.append((path, n, target))
        if not target.exists():
            errors.append(f'{path}:{n}: 链接缺失 {target}')
        elif fragment and target.is_file() and target.suffix.lower() == '.md':
            try:
                if fragment not in anchors(target.read_text('utf-8-sig')):
                    errors.append(f'{path}:{n}: 锚点缺失 {target}#{fragment}')
            except (OSError, UnicodeError) as exc:
                errors.append(f'{path}:{n}: 链接目标不可读 ({exc})')
    return errors, links


def check_templates(system: Path, installation_file: Path, retired=()):
    """Use the real mother in a disposable Home; never register its sample."""
    mother = system / 'Project-Template'
    for relative in ('README.md', 'AGENTS.md', 'INDEX.md', 'TEAM.md', 'HISTORY.md',
                     'Workstations/_workstation/ENTRY.md', 'Workstations/_workstation/TODO.md'):
        if not (mother / relative).is_file():
            raise ValueError(f'母版缺失：{mother / relative}')
    source_block(mother / 'AGENTS.md')
    with tempfile.TemporaryDirectory(prefix='paoe-template-') as directory:
        root = Path(directory) / 'Project'; home_id, project_id = '3002-s099', '3002'
        home = root / 'Workstations' / home_id
        home.mkdir(parents=True)
        for name in ('mailbox', 'notices'):
            (home / name).mkdir()
        for name in ('AGENTS.md', 'INDEX.md', 'TEAM.md', 'HISTORY.md'):
            text = (mother / name).read_text('utf-8-sig').replace('<home-id>', home_id).replace('<project-id>', project_id)
            (root / name).write_text(text, 'utf-8')
        todo = (mother / 'Workstations/_workstation/TODO.md').read_text('utf-8-sig')
        todo = todo.replace('<home-id>', home_id).replace('<project-id>', project_id)
        parsed = parse_todo(todo)
        if parsed['home_id'] != home_id or parsed['project_id'] != project_id:
            raise ValueError('TODO 母版身份与展开样例不同')
        (home / 'TODO.md').write_text(todo, 'utf-8')
        entry = render_fixed_entry(project={'id':project_id}, session={'id':home_id},
            workstation_path=home, entry_template=str(mother / 'Workstations/_workstation/ENTRY.md'),
            guide_root=str(system / 'Guide'), source_root=str(system / 'Core/code/personal-agent-os'),
            installation_file=str(installation_file))
        target = home / 'ENTRY.md'; target.write_text(entry, 'utf-8')
        errors, _ = inspect_markdown(target, retired)
        if errors:
            raise ValueError('\n'.join(errors))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-root', type=Path, required=True)
    parser.add_argument('--installation-file', type=Path, required=True)
    parser.add_argument('--project', action='append', default=[])
    parser.add_argument('--retired-locator', action='append', default=[], help='检查正文中的旧路径；命令示例不参与')
    parser.add_argument('--changed', type=Path, action='append', default=[], help='列当前检查范围内指向此文件的直接链接')
    parser.add_argument('--templates-only', action='store_true', help='仅母版与Guide，不代表真实项目已采用')
    args = parser.parse_args(argv)
    system, installation_file = args.system_root.resolve(), args.installation_file.resolve()
    errors, links = [], []
    try:
        mother = system / 'Project-Template'
        files = set(mother.rglob('*.md')) | set((system / 'Guide').rglob('*.md'))
        # The rendered sample checks these relative Home links with directories
        # created by init; the template itself is not an initialized Home.
        files.discard(mother / 'Workstations/_workstation/ENTRY.md')
        try:
            check_templates(system, installation_file, args.retired_locator)
            print('母版展开 / ENTRY / TODO v4：通过')
        except (OSError, ValueError, RuntimeError, WorkstationProblem) as exc:
            errors.append(f'母版展开失败：{exc}')
        if not args.templates_only:
            files.update(system / n for n in ('HOME.md','SYSTEM.md','PROJECTS.md','RESOURCES.md','MAINTENANCE.md'))
            registry = ProjectRegistry(installation_file)
            source = source_block(mother / 'AGENTS.md')
            for pid, agents in registered_targets(installation_file, args.project):
                state = inspect_target(pid, agents, source)
                print(f'AGENTS {pid}: {state.status}')
                if state.status != 'in-sync':
                    errors.append(f'{agents}: {state.status}；{state.reason}')
                record = registry.read_record(pid)
                project = agents.parent
                files.update(project / n for n in ('AGENTS.md','INDEX.md','TEAM.md','HISTORY.md'))
                for hid in record['homes']:
                    home = project / 'Workstations' / hid
                    files.add(home / 'ENTRY.md')
                    todo = parse_todo((home / 'TODO.md').read_text('utf-8-sig'))
                    if (todo['home_kind'],todo['home_id'],todo['project_id']) != ('project_agent',hid,pid):
                        errors.append(f'{home / "TODO.md"}: 身份不匹配')
            descriptor = load_installation_descriptor(installation_file)
            if descriptor.get('rooter_home'):
                rooter = Path(posix_windows_drive_locator(descriptor['rooter_home'])).expanduser()
                files.add(rooter / 'ENTRY.md')
            overview = system / 'PROJECTS.md'
            if overview.read_text('utf-8-sig') != render_overview(installation_file, overview):
                errors.append(f'{overview}: 聚合已过期；使用既有 --write 入口重建')
            else:
                print('PROJECTS 聚合：一致')
        for path in sorted(files):
            failures, found = inspect_markdown(path, args.retired_locator)
            errors.extend(failures); links.extend(found)
        changed = {p.resolve() for p in args.changed}
        for path, line, target in links:
            if target in changed:
                print(f'引用方：{path}:{line} -> {target}')
        for failure in errors:
            print(f'问题：{failure}', file=sys.stderr)
        print(f'关联检查：{"FAIL" if errors else "PASS"}；{len(files)} 文件，{len(links)} 本地链接')
        print('范围：本地机械检查；不验证外部网页、规则语义或原生唤醒，不修改真实文件。')
        return int(bool(errors))
    except (OSError, ValueError, RuntimeError, RegistryProblem) as exc:
        print(f'关联检查无法完成：{exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
