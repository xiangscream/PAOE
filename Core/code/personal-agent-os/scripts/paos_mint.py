"""Replaceable TODO/CAT checkpoint consumer hosted by the existing observer.

TODO owns definitions. The existing content journal owns explicit CAT events;
mint_runs records attempts, never business completion. Reservation commits
before native submission; an abandoned reservation stays uncertain.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from paos_content import changes_db, pack, record_version
from paos_installation import effective_data_root, load_installation_descriptor
from paos_attention_service import resolve_home_by_registry, AttentionServiceProblem
from paos_home import HomeProblem
from paos_phase_stop import executable_tasks
from paos_registry import ProjectRegistry, RegistryProblem
from paos_stage import task_snapshot, render
from paos_todo import read_todo, write_todo, TodoProblem


@contextmanager
def ledger(data):
    with changes_db(data) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS mint_runs (
            target_home TEXT NOT NULL, checkpoint_id TEXT NOT NULL,
            status TEXT NOT NULL, receipt TEXT NOT NULL,
            PRIMARY KEY(target_home,checkpoint_id))''')
        yield db


def reserve(data, home, key, source='', request_id=''):
    with ledger(data) as db:
        db.execute('BEGIN IMMEDIATE')
        keys = [key] + (['source:' + source] if source else [])
        attempt = 'check:' + pack([key, request_id]) if request_id else ''
        if attempt and db.execute('SELECT 1 FROM mint_runs WHERE target_home=? AND checkpoint_id=?',
                                  (home, attempt)).fetchone():
            return False
        previous = [db.execute('SELECT * FROM mint_runs WHERE target_home=? AND checkpoint_id=?',
                               (home, k)).fetchone() for k in keys]
        if any(previous):
            # A new explicit check can revisit a rejection, never a submitted
            # or unknown call. Replaying the same explicit request is inert.
            if not request_id or any(r and (r['status'] not in {'rejected', 'suppressed'}
                or json.loads(r['receipt']).get('check_request_id') == request_id) for r in previous):
                return False
        for k in keys:
            db.execute('INSERT OR REPLACE INTO mint_runs VALUES(?,?,?,?)',
                       (home, k, 'uncertain', pack({'reason': 'reserved_before_submit',
                                                  'retry': False, 'check_request_id': request_id,
                                                  'attempt_key': attempt})))
        if attempt:
            db.execute('INSERT INTO mint_runs VALUES(?,?,?,?)',
                       (home, attempt, 'uncertain', pack({'check_request_id': request_id})))
    return True


def finish(data, home, key, receipt):
    accepted = receipt.get('accepted')
    state = ('suppressed' if receipt.get('suppressed') else
             'submitted' if accepted is True else 'rejected' if accepted is False else 'uncertain')
    with ledger(data) as db:
        prior = db.execute('SELECT receipt FROM mint_runs WHERE target_home=? AND checkpoint_id=?',
                           (home, key)).fetchone()
        reservation = json.loads(prior[0])
        receipt = {**receipt, 'check_request_id': reservation.get('check_request_id', ''),
                   'attempt_key': reservation.get('attempt_key', '')}
        db.execute('UPDATE mint_runs SET status=?,receipt=? WHERE target_home=? AND checkpoint_id=?',
                   (state, pack(receipt), home, key))
        if receipt['attempt_key']:
            db.execute('UPDATE mint_runs SET status=?,receipt=? WHERE target_home=? AND checkpoint_id=?',
                       (state, pack(receipt), home, receipt['attempt_key']))
    return {'home': home, 'checkpoint_id': key, 'status': state, 'receipt': receipt}


def reminder_once(installation, home, source, submit):
    """Share one request identity with explicit Mail reminders, in both orders."""
    data = effective_data_root(load_installation_descriptor(installation))
    key = 'source:' + source
    if not reserve(data, home, key):
        return {'agent_id': home, 'state': 'already_reminded', 'accepted': False, 'retry': False}
    receipt = submit()
    finish(data, home, key, receipt)
    return receipt


def cat_event(data, room, message_id, name):
    event = dict(room=room, message_id=message_id, name=name)
    body = pack(event).encode('utf-8')
    with changes_db(data) as db:
        record_version(db, 'mint-cat:' + pack([room, message_id, name]),
                       hashlib.sha256(body).hexdigest(), 'mint_cat', 'cat', body=body)
    return event


def registered_homes(installation, emit=lambda event: None):
    descriptor = load_installation_descriptor(installation)
    data = effective_data_root(descriptor)
    registry = ProjectRegistry(installation)
    result = {}
    def include(ident):
        try:
            ref = resolve_home_by_registry(ident, installation_file=str(installation))
        except (HomeProblem, AttentionServiceProblem, RegistryProblem, OSError) as error:
            emit({'status': 'unavailable', 'home': ident, 'error': str(error)})
            return
        result[ref['home_id']] = ref
    for file in sorted((data / 'project-registry/projects').glob('*.json')):
        try:
            record = registry.read_record(file.stem)
        except RegistryProblem as error:
            emit({'status': 'unavailable', 'registry': str(file), 'error': str(error)})
            continue
        for ident in record['homes']:
            include(ident)
    if descriptor.get('rooter_home'):
        # Use the normal registry resolver rather than inventing a Rooter identity.
        include('rooter-001')
    return result


def arrange(home, task_id, *, ident, at='', on='manual', source='', cancel=False):
    path, before, doc, task = task_snapshot(home, task_id)
    point = next((p for p in task['checkpoints'] if p['id'] == ident), None)
    if cancel:
        if point is None:
            raise ValueError('检查点不存在')
        point['cancelled'] = True
    else:
        proposed = dict(id=ident, on=on, at=at, source_ref=source,
                        armed=on == 'manual', cancelled=False)
        if point is not None:
            if point != proposed:
                raise ValueError('检查点ID已存在；改期请取消原点并使用新ID')
        else:
            if task['state'] in {'done', 'cancelled'}:
                raise ValueError('已结束Task不能登记新的续工检查点')
            task['checkpoints'].append(proposed)
    write_todo(path, render(doc), expected_fingerprint=before)
    return {'ok': True, 'task_id': task_id, 'checkpoint_id': ident}


def native_wake(installation, home, prompt):
    from paos import execute_wake
    args = SimpleNamespace(wake_command='trigger', agent_id=home['home_id'],
        project_id=home['project_id'], prompt=prompt, model=None, root=None,
        installation_file=str(installation))
    return execute_wake(args, ProjectRegistry(installation), installation_path=installation)


def home_todo(home):
    doc = read_todo(Path(home['home_path']) / 'TODO.md')
    if (doc['home_kind'], doc['home_id'], doc['project_id']) != (
            home['home_kind'], home['home_id'], home['project_id']):
        raise ValueError('TODO身份与登记Home不一致：' + home['home_id'])
    return doc


class MintRunner:
    def __init__(self, installation, *, wake=native_wake, paused=(), emit=lambda event: None):
        self.installation = Path(installation)
        self.data = effective_data_root(load_installation_descriptor(installation))
        self.wake = wake
        self.emit = lambda event: emit({'event': 'mint', **event})
        self.paused = {resolve_home_by_registry(p, installation_file=str(installation))['home_id'] for p in paused}
        self.homes, self.docs = {}, {}
        self.dirty = True
        self.next_tick = 0
        self.observed = set()

    def changed(self, path):
        path = Path(path)
        if (path in {Path(h['home_path']) / 'TODO.md' for h in self.homes.values()}
                or path.parent == self.data / 'project-registry/projects'):
            self.dirty = True

    def directories(self):
        return {Path(h['home_path']) for h in self.homes.values()} | {self.data / 'project-registry/projects'}

    def refresh(self):
        self.homes = registered_homes(self.installation, self.emit)
        self.docs = {}
        for ident, home in self.homes.items():
            try:
                doc = home_todo(home)
            except (OSError, ValueError, TodoProblem) as error:
                self.emit({'home': ident, 'status': 'unavailable', 'error': str(error)})
                continue
            self.docs[ident] = doc
        self.dirty = False

    def candidates(self, now):
        with changes_db(self.data) as db:
            events = [json.loads(bytes(r[0]).decode('utf-8')) for r in db.execute(
                "SELECT v.body FROM changes c JOIN versions v ON v.version=c.version WHERE c.kind='mint_cat'")]
            stages = {(r['home'], r['operation']): json.loads(r['request'])
                      for r in db.execute('SELECT * FROM stages WHERE finished=1')}
        for owner, doc in self.docs.items():
            for task in doc['tasks']:
                for p in task['checkpoints']:
                    if p['armed'] and datetime.fromisoformat(p['at']) <= now:
                        yield owner, pack(['at', task['id'], p['id']]), p['source_ref'], task['id'], p['cancelled'], ''
                for item in task['notify_after']:
                    when, source = item['when'], item['source_ref']
                    matched = []
                    if when == 'task_done' and task['state'] == 'done':
                        matched = [('done', source)]
                    elif when == 'stage_delivered':
                        for ref in task['source_refs']:
                            req = stages.get((owner, ref.removeprefix('stage:'))) if ref.startswith('stage:') else None
                            if req and req['task'] == task['id'] and (not source or source in [ref, *req['artifacts'], *req['intents']]):
                                matched.append((ref, source))
                    elif when == 'cat_checkpoint' and task['state'] not in {'done', 'cancelled'}:
                        matched = [(pack(e), 'cat:' + e['room'] + ':' + e['message_id']) for e in events
                                   if source == 'cat:' + e['room'] + '#' + e['name']]
                    if matched:
                        try:
                            target = resolve_home_by_registry(item['to'], installation_file=str(self.installation))
                        except (HomeProblem, AttentionServiceProblem, RegistryProblem, OSError) as error:
                            self.emit({'status': 'unavailable', 'target': item['to'], 'source_home': owner,
                                       'task_id': task['id'], 'error': str(error)})
                            continue
                        for event, request_source in matched:
                            yield target['home_id'], pack([owner, task['id'], item, event]), source, '', False, request_source

    def step(self, now=None, monotonic=None, *, request_id='', only_home=None):
        now = now or datetime.now(timezone.utc)
        if monotonic is not None and monotonic < self.next_tick and not self.dirty:
            return []
        self.next_tick = (monotonic or 0) + 1
        if self.dirty:
            self.refresh()
        groups, rows, targets = {}, [], {}
        for target, key, source, task_id, cancelled, request_source in self.candidates(now):
            if only_home is not None and target != only_home:
                continue
            # A Mail event's original reminder shares this exact source lock.
            shared = request_source if request_source.startswith(('mail:', 'cat:')) else ''
            trigger = request_id
            if task_id and not trigger:
                doc = self.docs[target]
                task = next(t for t in doc['tasks'] if t['id'] == task_id)
                point = next(p for p in task['checkpoints'] if p['id'] == json.loads(key)[2])
                # Only an actual responsibility/arrangement transition or a
                # new formal stage is a new trigger, never an arbitrary save.
                trigger = pack(['todo', task_id, task['state'], task['waiting'], point,
                    [r for r in task['source_refs'] if r.startswith('stage:')],
                    doc['current']['waiting'] if 'task:' + task_id in doc['current']['context_refs'] else ''])
            observed = (target, key, trigger)
            if not request_id and observed in self.observed:
                continue
            if not reserve(self.data, target, key, shared, trigger):
                self.observed.add(observed)
                continue
            self.observed.add(observed)
            home = resolve_home_by_registry(target, installation_file=str(self.installation))
            targets[target] = home
            try:
                fresh = home_todo(home)
            except (OSError, ValueError, TodoProblem) as error:
                receipt = dict(accepted=False, state='home_unavailable', error=str(error))
                row = finish(self.data, target, key, receipt)
                if shared:
                    finish(self.data, target, 'source:' + shared, receipt)
                rows.append(row)
                self.emit(row)
                continue
            available = executable_tasks(fresh)
            # A timer resumes an executable responsibility. A new explicit
            # delivery is input even when its recipient is waiting for it.
            eligible = any(t['id'] == task_id for t in available) if task_id else True
            if task_id:
                p_id = json.loads(key)[2]
                live = next((p for t in fresh['tasks'] if t['id'] == task_id
                             for p in t['checkpoints'] if p['id'] == p_id), None)
                cancelled = (cancelled or live is None or live['cancelled'] or not live['armed']
                             or datetime.fromisoformat(live['at']) > now)
            else:
                owner, source_task, item, event = json.loads(key)
                try:
                    source_doc = home_todo(self.homes[owner])
                except (OSError, ValueError, TodoProblem) as error:
                    receipt = dict(accepted=False, state='source_unavailable', error=str(error))
                    row = finish(self.data, target, key, receipt)
                    if shared:
                        finish(self.data, target, 'source:' + shared, receipt)
                    rows.append(row)
                    self.emit(row)
                    continue
                live_source = next((t for t in source_doc['tasks'] if t['id'] == source_task), None)
                cancelled = (live_source is None or item not in live_source['notify_after']
                             or (item['when'] == 'task_done' and live_source['state'] != 'done')
                             or (item['when'] == 'cat_checkpoint' and live_source['state'] in {'done', 'cancelled'}))
            paused = target in self.paused or (self.data / 'mint-paused' / target).is_file()
            if cancelled or paused or not eligible:
                row = finish(self.data, target, key, dict(suppressed=True, accepted=False,
                    reason='cancelled' if cancelled else 'paused' if paused else 'no_executable_task'))
                if shared:
                    finish(self.data, target, 'source:' + shared, row['receipt'])
                self.emit(row)
                rows.append(row)
                continue
            groups.setdefault(target, []).append((key, source, shared))
        for target, points in groups.items():
            home = targets[target]
            references = []
            for key, source, shared in points:
                parts = json.loads(key)
                if parts[0] == 'at':
                    references.append(f"本人Task {parts[1]}，检查点 {parts[2]}，来源 {source}")
                else:
                    owner, source_task, item, event = parts
                    references.append(f"来源工位 {owner} / Task {source_task}，{item['when']}：{source}；原事件 {shared or event}")
            prompt = ('业务检查点已到。请从本人固定ENTRY和TODO恢复，实读匹配来源并继续已授权责任。\n'
                      + str(Path(home['home_path']) / 'ENTRY.md') + '\n'
                      + '\n'.join(references))
            from paos import CliError
            try:
                receipt = self.wake(self.installation, home, prompt)
            except (OSError, ValueError, CliError) as error:
                receipt = {'accepted': None, 'state': 'delivery_uncertain', 'error': str(error), 'retry': False}
            # Missing/not-configured is a rejection, not an invented success.
            if receipt.get('state') in {'not_configured', 'manual_required'}:
                receipt = {**receipt, 'accepted': False}
            for key, _, shared in points:
                row = finish(self.data, target, key, receipt)
                if shared:
                    finish(self.data, target, 'source:' + shared, receipt)
                self.emit(row)
                rows.append(row)
        return rows


def add_parser(sub):
    parser = sub.add_parser('mint', help='Explicit TODO/CAT checkpoints through the existing wake channel')
    commands = parser.add_subparsers(dest='mint_command', required=True)
    for name in ('arm', 'plan', 'cancel'):
        cmd = commands.add_parser(name)
        cmd.add_argument('home')
        cmd.add_argument('--task', required=True)
        cmd.add_argument('--id', required=True)
        if name != 'cancel':
            cmd.add_argument('--at', required=True, help='Explicit ISO time with timezone; no invented interval')
            cmd.add_argument('--source-ref', required=True)
        if name == 'plan':
            cmd.add_argument('--on', choices=['claim', 'doing', 'stage'], required=True)
    check = commands.add_parser('check')
    check.add_argument('home')
    check.add_argument('--request-id', required=True, help='New explicit check identity; replay never resends')
    check.add_argument('--paused-home', action='append', default=[])
    for name in ('pause', 'resume'):
        cmd = commands.add_parser(name)
        cmd.add_argument('home')
        if name == 'pause':
            cmd.add_argument('--reason', required=True)


def execute(args, installation):
    if args.mint_command in {'pause', 'resume'}:
        home = resolve_home_by_registry(args.home, installation_file=str(installation))
        data = effective_data_root(load_installation_descriptor(installation))
        path = data / 'mint-paused' / home['home_id']
        if args.mint_command == 'pause':
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args.reason, encoding='utf-8')
        else:
            path.unlink(missing_ok=True)
        return {'ok': True, 'home': home['home_id'], 'paused': path.is_file()}
    if args.mint_command == 'check':
        home = resolve_home_by_registry(args.home, installation_file=str(installation))
        return {'ok': True, 'runs': MintRunner(installation, paused=args.paused_home).step(
            request_id=args.request_id, only_home=home['home_id'])}
    home = resolve_home_by_registry(args.home, installation_file=str(installation))
    return arrange(home, args.task, ident=args.id, at=getattr(args, 'at', ''),
        source=getattr(args, 'source_ref', ''), on=getattr(args, 'on', 'manual'),
        cancel=args.mint_command == 'cancel')
