"""Delete short-lived recipient inputs after preserving their durable value.

The per-recipient tombstone is written before removal. It carries identity and
disposition, not message content; same-ID delivery must consult it even when a
previous deletion stopped halfway through.
"""
import json
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "paoe-input-deleted/v1"


def _check_notice_home(home, notice, installation_file=None):
    from paos_attention_service import _source_home_aliases
    ident = notice['home_id']
    if ((notice['home_kind'], notice.get('project_id', '')) != (home['home_kind'], home.get('project_id', ''))
            or ident not in {home['home_id'], *(_source_home_aliases(home, installation_file)
                                               if ident != home['home_id'] else ())}):
        raise ValueError('待清理 Notice 与登记工位身份不一致')


def _mail_source(home, message_id, installation_file=None):
    """Reuse the registered source reader; never rewrite old recipient or consumption facts."""
    from paos_attention_service import read_source_status, _source_home_aliases
    from paos_mail import parse_mail_frontmatter
    meta = parse_mail_frontmatter((Path(home['home_path']) / 'mailbox' / (message_id + '.md')).read_text(encoding='utf-8'))
    recipient = meta.get('recipient_agent_id')
    if (meta.get('message_id') != message_id or
            recipient not in {home['home_id'], *(_source_home_aliases(home, installation_file)
                                               if recipient != home['home_id'] else ())}):
        raise ValueError('待清理 Mail 与收件人身份不一致')
    notice = read_source_status(home_ref=home, source_kind='mail', source_ref=message_id,
                                installation_file=installation_file)['notice']
    _check_notice_home(home, notice, installation_file)
    return meta, notice


def _mail_archive(home, message_id, installation_file=None):
    """Read the existing archive marker using the same registered Home aliases."""
    from paos_attention_service import _source_home_aliases
    from paos_mail import _archive_path, _validate_message_id, read_mail_archive_home
    message_id = _validate_message_id(message_id)
    path = _archive_path(Path(home['home_path']), message_id)
    if not path.is_file():
        return None
    record = json.loads(path.read_text(encoding='utf-8'))
    recipient = record.get('recipient_agent_id') if isinstance(record, dict) else None
    aliases = (_source_home_aliases(home, installation_file)
               if recipient and recipient != home['home_id'] else ())
    # The existing reader still validates the full archive schema and identity.
    return read_mail_archive_home(Path(home['home_path']), home['home_id'], message_id,
                                  recipient_aliases=set(aliases))


def deletion_path(home, kind, ref):
    if kind not in {"mail", "notice"} or not ref or Path(ref).name != ref or any(c in ref for c in '/\\:'):
        raise ValueError("删除输入需要准确的 Mail 或 Notice ID")
    return Path(home) / ("mailbox" if kind == "mail" else "notices") / ".deleted" / (ref + ".json")


def read_deleted(home, kind, ref, home_id=None):
    # These existing archive locators are not message IDs. Their Notice still
    # has its own identity; do not reinterpret a historical locator as a file.
    if kind == "mail" and ref.startswith(("legacy-mail-file:", "rooter-mail-file:")):
        return None
    path = deletion_path(home, kind, ref)
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(record, dict) or record.get("schema") != SCHEMA
            or record.get("source_kind") != kind or record.get("source_ref") != ref
            or not record.get("home_id") or (home_id is not None and record["home_id"] != home_id)):
        raise ValueError(f"输入删除标记无效：{path}")
    return record


def delete_input(home, *, message_id="", notice_id="", disposition="consumed_deleted",
                 preserved_ref="", decision_ref="", decided_by="", installation_file=None):
    from paos_mail import _atomic_create, parse_mail_frontmatter
    from paos_notice import input_identity, notice_id_for, read_notice, notice_archive_files
    from paos_todo import read_todo

    if bool(message_id) == bool(notice_id):
        raise ValueError("必须且只能指定一个 Mail 或 Notice")
    if disposition not in {"consumed_deleted", "withdrawn", "superseded"}:
        raise ValueError("未知的输入收尾方式")
    if not preserved_ref.strip():
        raise ValueError("请先归位长期内容，提供保留原件或已完成业务的 --preserved-ref")
    if disposition != "consumed_deleted" and (not decision_ref.strip() or not decided_by.strip()):
        raise ValueError("撤回或替代须提供原 Owner/Human 的决定者和原决定")
    base = Path(home["home_path"])
    kind, ref = ("mail", message_id) if message_id else ("notice", notice_id)
    marker = deletion_path(base, kind, ref)
    existing = read_deleted(base, kind, ref, home["home_id"])
    replayed = existing is not None
    if kind == "mail" and _mail_archive(home, ref, installation_file):
        return {"source_ref": ref, "state": "archived_retained"}
    if existing:
        notice_id = existing["notice_id"]
    elif kind == "mail":
        from paos_attention_service import AttentionServiceProblem
        try:
            _, source = _mail_source(home, ref, installation_file)
            notice_id = source['notice_id']
        except AttentionServiceProblem as error:
            if error.code != 'notice_missing':
                raise
            notice_id = notice_id_for(input_identity(home_kind=home['home_kind'], home_id=home['home_id'],
                project_id=home.get('project_id', ''), source_kind='mail', source_ref=ref))

    anchors = {f"{kind}:{ref}", "notice:" + notice_id}
    from paos_context import local_source
    source_root = Path(home.get("project_root") or base)
    input_paths = {(base / "notices" / (notice_id + ".md")).resolve()}
    if kind == "mail":
        input_paths.add((base / "mailbox" / (ref + ".md")).resolve())

    def references_input(source):
        return source in anchors or local_source(source_root, source) in input_paths

    todo = read_todo(base / "TODO.md")
    dependents = [t["id"] for t in todo["tasks"] if t["state"] not in {"done", "cancelled"}
                  and any(references_input(source) for source in t["source_refs"])]
    if dependents:
        return {"source_ref": ref, "state": "active_dependency", "tasks": dependents}

    if existing is None:
        missing_notice = kind == "mail" and not (base / "notices" / (notice_id + ".md")).is_file()
        if missing_notice and disposition == "consumed_deleted":
            raise ValueError("Mail 缺少 Notice 消费证明；只能按原决定显式撤回或替代")
        notice = None if missing_notice else read_notice(base, notice_id)
        if notice is not None:
            _check_notice_home(home, notice, installation_file)
        if kind == "notice" and notice["source_kind"] == "mail":
            raise ValueError("Mail Notice 请用 --message-id 成组清理")
        if disposition == "consumed_deleted" and (not notice["read"] or notice["state"] != "handled"):
            raise ValueError("普通输入须先实际消费并办结；撤回/替代不能冒充消费")
        files = notice_archive_files(base, notice_id)
        sender = {}
        if kind == "mail":
            mail = base / "mailbox" / (ref + ".md")
            meta = parse_mail_frontmatter(mail.read_text(encoding="utf-8"))
            # Recipient validation already used the same registered source as the Notice.
            sender = {k: meta.get(k, "") for k in ("sender_kind", "sender_id")}
            files.append(mail)
            handled = base / "mailbox" / ".handled" / (ref + ".json")
            if handled.exists():
                files.append(handled)
        record = {"schema": SCHEMA, "home_id": home["home_id"],
                  "source_kind": kind, "source_ref": ref, "notice_id": notice_id,
                  "disposition": disposition, "notice_missing": missing_notice,
                  "was_read": None if missing_notice else bool(notice["read"]),
                  "was_handled": None if missing_notice else notice["state"] == "handled", **sender,
                  "executed_by": home["home_id"], "decided_by": decided_by,
                  "decision_ref": decision_ref, "preserved_ref": preserved_ref,
                  "deleted_at": datetime.now(timezone.utc).isoformat(),
                  "files": [p.relative_to(base).as_posix() for p in files]}
        marker.parent.mkdir(parents=True, exist_ok=True)
        _atomic_create(marker, json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        existing = read_deleted(base, kind, ref, home["home_id"])
    removed = []
    for name in existing["files"]:
        path = base / name
        if not path.resolve().is_relative_to(base.resolve()):
            raise ValueError(f"删除标记含工位外路径：{name}")
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            return {"source_ref": ref, "state": "cleanup_pending", "removed": removed,
                    "failed": name, "error": str(error), "retry": "使用相同输入再次执行 input-cleanup"}
        removed.append(name)
    return {"source_ref": ref, "notice_id": notice_id, "state": "deleted", "disposition": existing["disposition"],
            "replayed": replayed, "removed": removed}


def cleanup_task(home, task_id, preserved_ref="", *, source_roots=(), installation_file=None):
    from paos_attention_service import AttentionServiceProblem, _source_home_aliases
    from paos_todo import read_todo, TodoProblem
    from paos_mail import MailProblem
    from paos_notice import NoticeProblem, input_identity, notice_id_for, read_notice, handle_notice, notice_archive_files
    task = next((t for t in read_todo(Path(home["home_path"]) / "TODO.md")["tasks"] if t["id"] == task_id), None)
    if task is None:
        raise ValueError(f"收尾 Task 不存在：{task_id}")
    if task["state"] not in {"done", "cancelled"}:
        raise ValueError("任务尚未结束，不能收尾删除输入")
    results, deleted_notices = [], set()
    anchors = sorted(dict.fromkeys(task["source_refs"]), key=lambda value: not value.startswith("mail:"))
    covered_notices = set()
    active = []
    for anchor in anchors:
        kind, _, ref = anchor.partition(":")
        archive = _mail_archive(home, ref, installation_file) if kind == 'mail' else None
        if archive:
            results.append({"source_ref": ref, "state": "archived_retained"})
            for ident in {home['home_id'], archive['recipient_agent_id'], *_source_home_aliases(home, installation_file)}:
                covered_notices.add(notice_id_for(input_identity(home_kind=home["home_kind"], home_id=ident,
                    project_id=home.get("project_id", ""), source_kind="mail", source_ref=ref)))
        elif kind in {"mail", "notice"} and not (kind == "notice" and ref in covered_notices):
            if kind == 'notice' and ref in deleted_notices:
                continue
            existing = read_deleted(home['home_path'], kind, ref, home['home_id'])
            if existing:
                # Resume the already committed deletion, not a new preservation decision.
                result = delete_input(home, message_id=ref if kind == 'mail' else '',
                    notice_id=ref if kind == 'notice' else '', preserved_ref=existing['preserved_ref'],
                    installation_file=installation_file)
                results.append(result)
                covered_notices.add(existing['notice_id'])
                if result['state'] == 'deleted':
                    deleted_notices.add(result['notice_id'])
            else:
                active.append(anchor)
    anchors = active
    if not anchors:
        return {"task_id": task_id, "items": results,
                "complete": all(r['state'] in {'deleted', 'archived_retained'} for r in results)}
    preserved_ref = str(preserved_ref or "").strip()
    automatic = not preserved_ref
    preserved_ref = preserved_ref or str(task.get("artifact_ref") or "").strip()
    from paos_content import scoped_file
    from paos_context import local_source
    root = Path(home.get("project_root") or home["home_path"])
    try:
        if not preserved_ref:
            raise ValueError("缺少保全入口：请先归位成果或必要原话")
        preserved = (scoped_file(root, preserved_ref,
                     source_roots=source_roots if home["home_kind"] == "rooter" else ())
                     if automatic else local_source(root, preserved_ref))
        for anchor in anchors:
            kind, _, ref = anchor.partition(":")
            if kind not in {"mail", "notice"}:
                continue
            notice = (_mail_source(home, ref, installation_file)[1]['notice_id']
                       if kind == "mail" else ref)
            base = Path(home["home_path"])
            inputs = [base / "mailbox" / (ref + ".md"), base / "mailbox/.handled" / (ref + ".json"),
                      *notice_archive_files(base, notice)]
            if preserved_ref in {anchor, 'notice:' + notice} or preserved in {p.resolve() for p in inputs}:
                raise ValueError("保全入口不能是待删输入自身")
        if automatic:
            with preserved.open("rb") as stream:
                stream.read(1)
    except (OSError, ValueError, AttentionServiceProblem) as error:
        return {"task_id": task_id, "complete": False, "items": results + [
            {"source_ref": a.partition(":")[2], "state": "cleanup_pending", "error": str(error),
             "retry": f"paos input-cleanup {home['home_id']} --task {task_id} --preserved-ref <可读保全原件>"}
            for a in anchors if a.startswith(("mail:", "notice:"))]}
    for anchor in anchors:
        kind, _, ref = anchor.partition(":")
        if kind not in {"mail", "notice"}:
            continue
        if kind == "notice" and ref in deleted_notices:
            continue
        try:
            if kind == "mail" and _mail_archive(home, ref, installation_file):
                results.append({"source_ref": ref, "state": "archived_retained"})
                continue
            # An accepted Task can finish its own claimed/read input. It cannot
            # manufacture consumption of other inputs merely linked to it.
            notice_id = (_mail_source(home, ref, installation_file)[1]['notice_id']
                         if kind == "mail" else ref)
            if not read_deleted(home["home_path"], kind, ref):
                notice = read_notice(Path(home["home_path"]), notice_id)
                _check_notice_home(home, notice, installation_file)
                if notice["read"] and notice.get("claim_task_ref") == task_id and notice["state"] != "handled":
                    handle_notice(home_path=Path(home["home_path"]), notice_id=notice_id,
                                  resolution=f"Task {task_id} 已完成，结果见本人 TODO", action_ref=task_id)
            result = delete_input(home, message_id=ref if kind == "mail" else "",
                                  notice_id=ref if kind == "notice" else "", preserved_ref=preserved_ref,
                                  installation_file=installation_file)
            if result["state"] == "deleted":
                deleted_notices.add(result["notice_id"])
        except (OSError, ValueError, NoticeProblem, MailProblem, TodoProblem, AttentionServiceProblem) as error:
            result = {"source_ref": ref, "state": "cleanup_pending", "error": str(error)}
        results.append(result)
    return {"task_id": task_id, "items": results,
            "complete": all(r["state"] in {"deleted", "archived_retained"} for r in results)}


def cleanup_completed_task(home, task_id, preserved_ref="", *, source_roots=(), installation=None):
    """A committed business result survives a pending input cleanup."""
    from paos_todo import TodoProblem
    from paos_registry import RegistryProblem
    from paos_installation import InstallationProblem
    from paos_mail import MailProblem
    from paos_notice import NoticeProblem
    from paos_attention_service import AttentionServiceProblem
    try:
        if installation is not None and home["home_kind"] == "rooter" and not str(preserved_ref or '').strip():
            from paos_phase_cli import _project_roots
            from paos_installation import effective_data_root, load_installation_descriptor
            source_roots = _project_roots(installation, effective_data_root(load_installation_descriptor(installation)))
        return cleanup_task(home, task_id, preserved_ref, source_roots=source_roots, installation_file=installation)
    except (OSError, ValueError, TodoProblem, RegistryProblem, InstallationProblem, MailProblem, NoticeProblem,
            AttentionServiceProblem) as error:
        return {"task_id": task_id, "complete": False, "state": "cleanup_pending", "error": str(error),
                "retry": f"paos input-cleanup {home['home_id']} --task {task_id} --preserved-ref <可读保全原件>"}


def add_cleanup_parser(sub):
    cmd = sub.add_parser("input-cleanup", help="Delete short-lived recipient inputs; preserve deduplication")
    cmd.add_argument("home")
    target = cmd.add_mutually_exclusive_group(required=True)
    target.add_argument("--task")
    target.add_argument("--message-id")
    target.add_argument("--notice-id")
    cmd.add_argument("--preserved-ref", required=True, help="Durable content or completed business reference")
    cmd.add_argument("--disposition", choices=["consumed_deleted", "withdrawn", "superseded"], default="consumed_deleted")
    cmd.add_argument("--decision-ref", default="")
    cmd.add_argument("--decided-by", default="")


def execute_cleanup(args, installation):
    from paos_attention_service import resolve_home_by_registry
    home = resolve_home_by_registry(args.home, installation_file=str(installation))
    if args.task:
        if args.disposition != "consumed_deleted":
            raise ValueError("撤回/替代只接受原决定明确指向的单条输入")
        result = cleanup_task(home, args.task, args.preserved_ref, installation_file=installation)
    else:
        result = delete_input(home, message_id=args.message_id or "", notice_id=args.notice_id or "",
                              disposition=args.disposition, preserved_ref=args.preserved_ref,
                              decision_ref=args.decision_ref, decided_by=args.decided_by, installation_file=installation)
    complete = result.get("complete", result.get("state") in {"deleted", "archived_retained"})
    return {"ok": complete, "schema": "paoe-input-cleanup/v1", **result}
