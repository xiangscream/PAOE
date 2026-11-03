"""Create a human-readable System Vault; never write PAOE domain originals.

Dry-run by default. Existing human pages are left alone. Only intact generated
snapshots can be explicitly refreshed. Obsidian registration is a separate UI step.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from urllib.parse import quote
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code/personal-agent-os/scripts'))
from paos_installation import InstallationProblem, effective_data_root, load_installation_descriptor
from paos_library import LibraryProblem, load_library_roots
from paos_registry import ProjectRegistry
from paos_workstation import posix_windows_drive_locator

MARKER = 'PAOE System Vault / navigation only / v1\n'
SIGNATURE = re.compile(r'\A<!-- PAOE SNAPSHOT sha256:([a-f0-9]{64}) -->\n')


class SystemVaultProblem(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def disk(value):
    return Path(posix_windows_drive_locator(str(value))).expanduser().resolve()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def git_value(path, *args):
    try:
        result = subprocess.run(['git', '-C', str(path), *args], capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=10)
        return result.stdout.strip() if result.returncode == 0 else 'unverified'
    except (OSError, subprocess.TimeoutExpired):
        return 'unverified'


def link(path, label='原件', obsidian=False):
    path = disk(path)
    available = path.exists()
    label = str(label).replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]').replace('|', '\\|')
    text = f'[{label}](<{path.as_uri()}>)'
    if obsidian and path.is_file() and path.suffix.lower() == '.md':
        text += f' · [Obsidian候选](obsidian://open?path={quote(str(path), safe="")})'
    return text + ('' if available else '（Unavailable；保留登记，不创建替代物）')


def inspect_installation(installation_file, roots_file=None):
    path = disk(installation_file)
    installation = load_installation_descriptor(path)
    if not installation.get('configured'):
        raise ValueError(f'安装未登记：{path}')
    # Deliberately use this descriptor, not another installation's ambient env.
    roots_path = disk(roots_file or installation['library_roots_config'])
    roots = load_library_roots(roots_path, validate_roots=False)
    data = disk(effective_data_root(installation))
    registry_root = data / 'project-registry/projects'
    try:
        if not data.is_dir():
            raise SystemVaultProblem('registry_unavailable', f'data_root不可访问，不能判断项目数量：{data}')
        if not registry_root.is_dir():
            raise SystemVaultProblem('registry_uninitialized', f'Registry目录缺失或未初始化，不能解释为空名册：{registry_root}')
        # iterdir surfaces access failures; a glob can silently look empty.
        entries = list(registry_root.iterdir())
    except OSError as exc:
        raise SystemVaultProblem('registry_unavailable', f'Registry无法读取：{registry_root}（{type(exc).__name__}）') from exc
    registry = ProjectRegistry(path)
    records = []
    # Every JSON-shaped entry must be checked by the authoritative reader.
    # is_file() would silently hide directories and some inaccessible records.
    for record in sorted(p for p in entries if p.suffix.lower() == '.json'):
        project = registry.read_record(record.stem)
        root = disk(project['root_path'])
        project['available'] = root.is_dir()
        project['registry_path'] = str(record)
        project['git_root'] = git_value(root, 'rev-parse', '--show-toplevel') if root.is_dir() else 'unavailable'
        project['entry_candidates'] = [str(p) for p in sorted(root.glob('*.md'))] if root.is_dir() else []
        records.append(project)
    source = disk(installation['source_root'])
    return {'at': datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
            'installation_file': str(path), 'roots_file': str(roots_path),
            'source_root': str(source), 'data_root': str(data),
            'rooter_home': installation.get('rooter_home') or '',
            'registry_root': str(registry_root),
            'source_commit': git_value(source, 'rev-parse', 'HEAD'),
            'source_git_root': git_value(source, 'rev-parse', '--show-toplevel'),
            'python': sys.executable, 'roots': roots, 'projects': records}


def protected_roots(state):
    values = [state['source_root'], state['data_root'], state['rooter_home'],
              state['source_git_root'], state['installation_file'], state['roots_file']]
    values += [state['roots'].get(k, '') for k in ('workflow_root', 'skill_root', 'tool_catalog')]
    values += [p['root_path'] for p in state['projects']]
    return [disk(v) for v in values if v and v != 'unverified']


def snapshot(title, state, body):
    text = (f'# {title}\n\n> 只读导航快照 · {state["at"]}\n'
            f'> 来源：{state["installation_file"]}；{state["roots_file"]}；Project Registry。\n'
            '> 权威原件在链接目标；此处不是配置或业务状态写者。文件存在性已核，Obsidian候选链接仍需实际打开验证。\n\n'
            + body.rstrip() + '\n')
    return f'<!-- PAOE SNAPSHOT sha256:{digest(text.encode())} -->\n' + text


def rendered_snapshots(state):
    argv = [state['python'], '-X', 'utf8', str(disk(state['source_root']) / 'scripts/paos.py'),
            '--installation-file', state['installation_file'], '--library-roots-config', state['roots_file']]
    command = ('& ' + ' '.join("'" + x.replace("'", "''") + "'" for x in argv)) if os.name == 'nt' else shlex.join(argv)
    language = 'powershell' if os.name == 'nt' else 'sh'
    machine = f'实际安装提交：`{state["source_commit"]}`。\n\n'
    machine += '| 资产 | 权威定位 |\n|---|---|\n'
    if state['source_git_root'] != 'unverified':
        machine += f'| Portable仓库 | {link(state["source_git_root"], "仓库目录")} · `{state["source_git_root"]}` |\n'
    for label, key in [('Portable源码', 'source_root'), ('安装描述', 'installation_file'),
                       ('库登记', 'roots_file'), ('安装数据', 'data_root')]:
        machine += f'| {label} | {link(state[key])} · `{state[key]}` |\n'
    machine += f'\nCLI调用前缀（从任何目录追加子命令）：\n\n```{language}\n{command}\n```\n'
    machine += '\n原生接收器说明：' + link(disk(state['source_root']) / 'docs/CODEX-SELF-REMINDER.md', '当前安装的说明') + '\n'
    projects = f'Registry根已确认可读：{link(state["registry_root"])}；本次读取 {len(state["projects"])} 条登记。\n\n'
    projects += '| Project | Vault目录 | Registry原件 | Coordinator | Git根 |\n|---|---|---|---|---|\n'
    agents = '| Project / Home | ENTRY | TODO |\n|---|---|---|\n'
    for project in state['projects']:
        root = disk(project['root_path'])
        projects += (f'| {project["id"]} | {link(root, root.name)} | {link(project["registry_path"])} | '
                     f'{project["coordinator_home_id"]} | `{project["git_root"]}` |\n')
        for home in project['homes']:
            agents += f'| {project["id"]} / {home} | {link(root / "Workstations" / home / "ENTRY.md", "入口", True)} | {link(root / "Workstations" / home / "TODO.md", "当前行动", True)} |\n'
    projects += '\n## 项目原有入口\n\n下列仅为实际顶层Markdown文件，不据文件名判定哪篇是业务最新口径。\n\n'
    for project in state['projects']:
        projects += f'### {project["id"]}\n\n'
        projects += '\n'.join('- ' + link(p, Path(p).name, True) for p in project['entry_candidates']) or 'Unavailable；保留Registry。'
        projects += '\n\n'
    agents += '\n## Rooter\n\n安装级Home，不是Project成员。\n\n'
    if state['rooter_home']:
        rooter = disk(state['rooter_home'])
        agents += f'- {link(rooter / "ENTRY.md", "Rooter ENTRY")}\n- {link(rooter / "TODO.md", "Rooter TODO")}\n'
    else:
        agents += '未登记。\n'
    agents += '\n本目录不复制TODO内容、Mail正文、Notice状态、原生Session ID或凭据。\n'
    resources = ''
    for kind, key in [('Workflow', 'workflow_root'), ('Skill', 'skill_root'), ('Tool', 'tool_catalog')]:
        raw = state['roots'].get(key) or ''
        resources += f'## {kind}\n\n'
        if not raw:
            resources += '未登记。\n\n'
            continue
        root = disk(raw)
        resources += f'`{raw}` · {link(root, "登记位置")}\n\n'
        if kind != 'Tool':
            resources += '- ' + link(root / 'CATALOG.md', '派生Catalog', True) + '\n'
        if kind == 'Workflow':
            for relative in ('Workflows/wf-agent-work-cycle.md', 'Guides/guide-work-method.md',
                             'Guides/ops-entry.md', 'Guides/guide-paos-cat-operations.md',
                             'Guides/guide-rooter-installation.md', 'Guides/guide-upgrade-adoption.md',
                             'Templates/workstation-entry.md', 'Templates/workstation-todo.md'):
                resources += '- ' + link(root / relative, relative, True) + '\n'
        if kind == 'Skill' and root.is_dir():
            resources += '\n'.join('- ' + link(p, p.parent.name, True) for p in sorted(root.glob('*/SKILL.md'))) + '\n'
        resources += '\n'
    return {'Installation/CURRENT-MACHINE.md': snapshot('当前安装', state, machine),
            'Projects/PROJECT-INDEX.md': snapshot('项目定位', state, projects),
            'Agents/AGENT-DIRECTORY.md': snapshot('工位导航', state, agents),
            'Libraries/RESOURCES.md': snapshot('实际登记资源', state, resources)}


def human_pages():
    return {
        'HOME.md': '''# PAOE · 系统总入口

打开原件，理解它属于谁，再在原处维护。此库是系统说明与导航；项目、方法和当前行动继续留在各自原件。

| 想做什么 | 从这里进入 |
|---|---|
| 看整体关系 | [[Architecture/SYSTEM-MAP]] · [[Architecture/DATA-OWNERSHIP]] |
| 找代码、安装配置和CLI | [[Installation/CURRENT-MACHINE]] · [[Installation/PATHS]] · [[Architecture/MODULE-MAP]] |
| 找共享方法和工具 | [[Libraries/WORKFLOW]] · [[Libraries/SKILL]] · [[Libraries/TOOL]] · [[Libraries/RESOURCES]] |
| 打开项目与工位 | [[Projects/PROJECT-INDEX]] · [[Agents/AGENT-DIRECTORY]] · [[Agents/ROOTER]] |
| 理解联系和唤醒 | [[Runtime/CONTACT]] |
| 看可选画板 | [[Frontend/BOARD]] |
| 日常使用、恢复和备份 | [[Operations/DAILY-USE]] · [[Operations/RECOVERY]] · [[Operations/BACKUP]] |
| 开始学习并写自己的笔记 | [[Learning/ROADMAP]] · [[Learning/NOTES/README]] |

**可手改**：本页及解释、学习笔记。**带时间戳的快照**：定位导航可显式刷新，不能在这里改机器配置或任务。外部原件的Obsidian候选链接只有实际打开后才算验证；也提供文件系统路径。
''',
        'Architecture/SYSTEM-MAP.md': '''# 系统关系

```mermaid
flowchart TB
  H[Human / Obsidian] --> S[System Vault 解释与导航]
  S --> I[Installation / Registry 定位原件]
  S --> L[Shared Workflow / Skill / Tool 原件]
  I --> P[各盘 Project Vault]
  P --> A[Agent Home: ENTRY / TODO / Mail / Notice]
  I --> R[安装级 Rooter]
  CLI[PAOE CLI] --> I
  CLI --> A
  B[可选 Board] --> CLI
  A -.显式配置及一次提醒.-> RT[Codex / OpenCode 等 Harness]
```

核心集中、项目可分散，靠Registry绝对路径定位。现有项目是否有独立Obsidian/Git，应看[[Projects/PROJECT-INDEX]]中的实际根；本轮不搬项目、不拆历史。
''',
        'Architecture/DATA-OWNERSHIP.md': '''# 原件归属与人工编辑

| 事实 | 原件 / 写者 | 这里如何使用 |
|---|---|---|
| 项目位置和成员 | Registry五字段；登记CLI | 只链接定位 |
| 项目共识、材料、成果 | Project正文；项目约定 | 打开对应原件编辑 |
| 当前行动 | 本人Home TODO v4；现有写者 | 只链接，不复制任务表 |
| Workflow / Skill / Tool | 各登记库源文件 | 找到原件再读和修改 |
| 安装路径 / 原生连接 | Installation / Contact | 解释字段，不复制另一份配置 |
| 输入和处理事实 | Mail原件 / Notice写者 | 不在本库改投递内容或处理状态 |

普通项目文稿、解释和学习笔记可直接编辑。TODO的结构化区域仍遵守v4格式和指纹写入；机器配置先核schema与影响。Catalog和本库快照不是新的权威。详见[[Installation/PATHS]]、[[Operations/DAILY-USE]]。
''',
        'Architecture/MODULE-MAP.md': '''# 如何找到实现

源码位置与版本见[[Installation/CURRENT-MACHINE]]。正常入口为source_root/scripts/paos.py；它解析命令，调用paos_registry、paos_home、paos_todo、paos_attention_service、paos_library等既有领域模块。

Portable负责本机定位；Project Registry只保存位置和成员；Home写者负责TODO/Mail/Notice；Contact/Adapter负责显式原生提醒；front只展示和调用现有入口。学习时从一条真实调用链开始，不先通读历史框架。

[当前学习基线与路线](https://github.com/xiangscream/PAOS-portable/blob/b8d6263e4da7b045c48a6bb2acbd4230d83c653a/LEARNING-BASELINE.md)描述的是远端文档基线，不能替代本机实际安装版本。
''',
        'Installation/PATHS.md': '''# 路径配置怎么读

实际文件、路径与CLI前缀见[[CURRENT-MACHINE]]。installation.json中的source_root指程序，data_root指安装数据，library_roots_config指共享库登记，rooter_home指安装级工位。库登记分别指Workflow、Skill和Tool Catalog；它们不必相邻。

Project Registry每条仅含schema、id、root_path、homes、coordinator_home_id。root_path可在不同磁盘；缺盘应记Unavailable，不能注销、换路径或新建替代项目。项目不存在与登记不存在是两回事。

这些JSON可直接阅读；修改时优先使用安装/登记CLI，先核同版--help、schema和作用范围。本库只给说明及快照，不保存第二份可编辑路径配置。
''',
        'Libraries/WORKFLOW.md': '''# Workflow 与指南

实际根和关键原件见[[RESOURCES#Workflow]]。Workflows保存通用工作组织和多步方法；Guides负责导航与操作说明；Templates给格式参考。通用行为正文是wf-agent-work-cycle，ENTRY只链接它。

使用[[Installation/CURRENT-MACHINE]]的CLI前缀追加`library search "问题关键词" --kind workflow`；打开返回的source_path并读正文。Catalog可由源文件重建，不手抄成另一套方法库。
''',
        'Libraries/SKILL.md': '''# 专业 Skill

实际根和当前源文件见[[RESOURCES#Skill]]。Skill是专业判断/操作方法；用途不匹配时不强行套用。用当前CLI的`library search "任务关键词" --kind skill`定位，读返回的源文件；本页不复制Skill正文。
''',
        'Libraries/TOOL.md': '''# 工具说明与实际可用性

Tool原件见[[RESOURCES#Tool]]。Catalog有说明、本机有命令、某Runtime已授权、当前Runtime实测调用成功，是四种不同事实。旧电脑路径及历史核实记录不证明本机可调用；这里不扫描或展示登录凭据。

用当前CLI的`library tools`读取目录。实际调用遵循对应说明和当前Runtime工具；只为当前任务核必要能力，不为展示而触发外部写入。
''',
        'Agents/ROOTER.md': '''# 安装级 Rooter

原件位置见[[AGENT-DIRECTORY#Rooter]]。Rooter维护安装、共享资源定位及运行入口，不属于任何Project。项目目标与职责归Coordinator；成员维护自己的当前行动。

向已登记Rooter提交需要接续的请求，仍用`agent send <本人项目ID> --to rooter-001 ... --remind`。完整参数、失败和结果未知处理读登记Workflow中的OPS及操作指南，不手工猜mailbox目录。
''',
        'Runtime/CONTACT.md': '''# Runtime、联系与唤醒

Codex / OpenCode等Harness负责模型执行。Home、Contact与原生会话是不同对象。配置存在不等于在线；入口prepared不等于已送达；Mail保存不等于已消费。

本库不保存原生Session ID、凭据、pipe或端口配置。沿本人ENTRY和正式wake status/contact status读取当前事实，按已登记的操作指南恢复。自动SessionStart的历史缺口不因本库建成而视为解决。

CAT是可选外部协作服务。未配置时保持未配置；本机文件操作不依赖它。不要为展示而触发Wake或创建房间。
''',
        'Frontend/BOARD.md': '''# 可选 PAOE Board

Board是关系和工位状态的辅助视图，System Vault是Human总入口。Board读Registry、项目入口、Home和Library；少量动作经既有CLI/CAT执行，不另存任务事实。

从实际Portable目录运行`python portable.py serve`，默认只监听127.0.0.1:8780。启动后再[打开本地画板](http://127.0.0.1:8780/)。若端口冲突，查同版serve --help选另一端口，不杀占用进程。本页不表示服务已启动。

项目/工位选择和阅读不会替成员接单。发送消息、留信或建CAT房间有写入副作用；不要为了导航演示点击这些动作。关闭Board不影响Obsidian或CLI。
''',
        'Operations/DAILY-USE.md': '''# 从入口继续真实工作

Human可从[[../HOME]]找到项目或方法原件，再在原处阅读和编辑。Agent从本人ENTRY进入登记库中的工作循环、本人TODO和当前原输入，确认已授权的下一步。

用peers/team找登记同事，按需打开TEAM职责原件；用library search找方法，打开source_path。具体恢复、TODO更新、求助、Notice处理及回到主线的规则只维护在登记Workflow中；见[[../Libraries/RESOURCES]]。

不为证明配置成功制造签收、空ACK或长期行为率统计。
''',
        'Operations/RECOVERY.md': '''# 原件不可用时

先确认Unavailable的是目录、文件、磁盘、登记还是Runtime，不把空结果当全局没有任务。保留原登记和原路径，检查挂载/实际文件，再沿原入口恢复；不要自动重建或覆盖项目。

Obsidian候选链接打不开时，使用导航中的准确路径，在文件管理器检查原件；文件所属目录可能尚未登记为Obsidian Vault。不要复制原件到本库来修链接。CLI参数以当前安装--help为准。

机器配置或Runtime故障找Rooter，业务口径与角色归属找Coordinator。新的软件安装、Vault移动或绑定变更不属于普通导航刷新。
''',
        'Operations/BACKUP.md': '''# 备份与版本边界

System Vault的解释页和学习笔记是本库内容，可独立备份；定位快照可从原件重新生成。备份本库不等于备份Project、共享方法、代码或Runtime。各层保持各自历史，不把它们汇总成一份工作状态库。

项目移动先staged-copy、核对内容和历史，再明确cutover；本轮不执行迁移。不要为整齐清理旧目录、未提交修改或别人的工作树。

刷新快照前先查看差异；工具拒绝覆盖人工改过的快照。把说明写在解释页或学习笔记，原始文件继续在原处维护。
''',
        'Learning/ROADMAP.md': '''# 从本机环境到软件实现

先从HOME找到安装、库、项目、工位与前端，再学习一条调用链。远端[学习基线](https://github.com/xiangscream/PAOS-portable/blob/b8d6263e4da7b045c48a6bb2acbd4230d83c653a/LEARNING-BASELINE.md)提供M0至M7路线；实际执行版本见[[../Installation/CURRENT-MACHINE]]。

学习实验在隔离fixture中进行，不用生产TODO、Mail、Contact或Registry练习。自己的理解和问题放[[NOTES/README]]所在目录，本工具不会覆盖这些笔记。
''',
        'Learning/NOTES/README.md': '# 我的学习笔记\n\n在此创建普通Markdown，记录自己的理解、问题与实验链接。笔记不成为共享方法或机器配置的第二份原件。\n',
    }


def write_vault(state, output, *, apply=False, refresh=False):
    output = Path(output).expanduser().absolute()
    if output.is_symlink():
        raise ValueError('目标不能是符号链接')
    output = output.resolve()
    for root in protected_roots(state):
        if output == root or output.is_relative_to(root) or root.is_relative_to(output):
            raise ValueError(f'目标与权威原件重叠：{root}')
    exists = output.exists()
    if exists and (not output.is_dir() or not (output / '.paoe-system-vault').is_file()
                   or (output / '.paoe-system-vault').read_text(encoding='utf-8') != MARKER):
        raise ValueError('目标已存在且不是本工具创建的System Vault；不覆盖')
    pages = human_pages()
    snapshots = rendered_snapshots(state)
    planned = {}
    expected = {}
    for name, text in {**pages, **snapshots}.items():
        path = output / name
        if not path.resolve().is_relative_to(output):
            raise ValueError(f'目标链接逃逸：{name}')
        if path.exists():
            if name not in snapshots or not refresh:
                continue
            current = path.read_text(encoding='utf-8')
            match = SIGNATURE.match(current)
            if not match or digest(current[match.end():].encode()) != match.group(1):
                raise ValueError(f'快照已有人工修改，请保留并审阅：{name}')
            expected[name] = digest(path.read_bytes())
        else:
            expected[name] = None
        planned[name] = text
    result = {'output': str(output), 'apply': apply, 'new_vault': not exists,
              'files': list(planned), 'domain_writes': False}
    if not apply or not planned:
        return result
    if not exists:
        if not output.parent.is_dir():
            raise ValueError('目标父目录不存在；请明确选择已存在的工作位置')
        stage = output.with_name(f'.{output.name}.candidate-{uuid.uuid4().hex}')
        stage.mkdir()
        for name, text in planned.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8', newline='\n')
        (stage / '.paoe-system-vault').write_text(MARKER, encoding='utf-8')
        if output.exists():
            raise ValueError(f'目标在生成期间出现，保留候选于{stage}')
        stage.rename(output)
    else:
        for name, text in planned.items():
            path = output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
            temporary.write_text(text, encoding='utf-8', newline='\n')
            current = digest(path.read_bytes()) if path.exists() else None
            if current != expected[name]:
                raise ValueError(f'目标在写入前变化，保留候选于{temporary}')
            os.replace(temporary, path)
    return result


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation-file', required=True)
    parser.add_argument('--library-roots-config')
    parser.add_argument('--output', required=True)
    parser.add_argument('--apply', action='store_true', help='Create the new System Vault; otherwise dry-run')
    parser.add_argument('--refresh-snapshots', action='store_true', help='Explicitly refresh intact snapshots; never replace human pages')
    args = parser.parse_args(argv)
    try:
        state = inspect_installation(args.installation_file, args.library_roots_config)
        result = write_vault(state, args.output, apply=args.apply, refresh=args.refresh_snapshots)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, InstallationProblem, LibraryProblem) as exc:
        print(json.dumps({'ok': False, 'error': str(exc), 'error_code': getattr(exc, 'code', 'system_vault_error')}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
