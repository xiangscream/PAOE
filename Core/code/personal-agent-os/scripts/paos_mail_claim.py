"""Quiet Mail claim and result linkage to the recipient's TODO v4.

Claim checks the exact source Notice before touching TODO. Result only closes a
Task that was auto-created for this source; a pre-existing broad Task is never
auto-completed. Current.Waiting is cleared only on an exact Task/message match.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from paos_attention_service import (
    handle_mail_input as attention_handle_mail_input,
    mark_input_read,
    read_project_mail_input as attention_read_project_mail_input,
)
from paos_notice import (
    claim_notice, handle_notice, input_identity, normalize_notice_resolution,
    notice_id_for, read_notice,
)
from paos_todo import parse_todo, render_todo, write_todo


def _task_id_for(message_id: str) -> str:
    digest = hashlib.sha256(message_id.encode("utf-8")).hexdigest()[:12]
    return f"T-MAIL-{digest}"


def _source_ref(message_id: str) -> str:
    return f"mail:{message_id}"


def _load_todo(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    return parse_todo(raw.decode("utf-8-sig")), hashlib.sha256(raw).hexdigest()


def _ensure_task(*, doc: dict[str, Any], todo_path: Path, fingerprint: str,
                 task_id: str, title: str, source_ref: str) -> tuple[str, bool, bool]:
    tasks = [dict(task) for task in doc.get("tasks") or []]
    selected: dict[str, Any] | None = None
    created = False
    if task_id:
        selected = next((task for task in tasks if task["id"] == task_id), None)
        if selected is None:
            raise ValueError(f"Tasks missing {task_id}")
    else:
        selected = next(
            (task for task in tasks if source_ref in (task.get("source_refs") or [])),
            None,
        )
        if selected is None:
            task_id = _task_id_for(message_id=source_ref)
            selected = {
                "id": task_id, "title": title or "claim source",
                "state": "doing", "waiting": "", "result": "",
                "artifact_ref": "", "source_refs": [], "acceptance_refs": [],
                "notify_after": [],
            }
            tasks.append(selected)
            created = True
    changed = source_ref not in (selected.get("source_refs") or [])
    if changed:
        selected["source_refs"] = [*(selected.get("source_refs") or []), source_ref]
        text = render_todo(
            home_kind=doc["home_kind"], home_id=doc["home_id"],
            project_id=doc["project_id"], pinned=doc.get("pinned", ""),
            objective=doc["current"]["objective"],
            next_action=doc["current"]["next_action"],
            waiting=doc["current"].get("waiting", ""),
            inflight=doc["current"].get("inflight", ""),
            context_refs=doc["current"].get("context_refs", []),
            result_refs=doc["current"].get("result_refs", []),
            updated_at=doc["current"].get("updated_at", ""),
            tasks=tasks,
        )
        write_todo(todo_path, text, expected_fingerprint=fingerprint)
    return str(selected["id"]), changed, created


def claim_mail(*, root: Path, project: dict[str, Any], agent_id: str,
               message_id: str, task_id: str = "", title: str = "",
               recipient_aliases: set[str] | None = None) -> dict[str, Any]:
    read = attention_read_project_mail_input(
        root=root, project=project, agent_id=agent_id, message_id=message_id,
        recipient_aliases=recipient_aliases)
    home = read["home"]
    notice = read["notice"]
    if notice.get("state") == "handled":
        raise ValueError("Mail 已完结，不能再次接手")
    existing_task = str(notice.get("claim_task_ref") or "")
    if notice.get("claimed"):
        if task_id and task_id != existing_task:
            raise ValueError(
                f"Mail 已接手到 {existing_task}，不能改挂 {task_id}")
        marked = mark_input_read(
            home_ref=home, notice_id=notice["notice_id"],
            recipient_aliases=recipient_aliases)
        claimed = claim_notice(
            home_path=Path(home["home_path"]), notice_id=notice["notice_id"],
            claimant_home_kind=home["home_kind"], claimant_home_id=home["home_id"],
            claimant_project_id=home["project_id"], task_ref=existing_task,
            action_ref=_source_ref(message_id),
            task_auto_created=bool(notice.get("claim_task_auto_created")),
            claimant_aliases=recipient_aliases or set())
        return {
            "schema": "paos-mail-claim/v1", "message_id": message_id,
            "home": home, "mail": read["mail"], "notice": claimed,
            "read": marked.get("notice", {}), "task_id": existing_task,
            "task_changed": False, "claim_changed": False, "quiet": True,
        }

    home_path = Path(home["home_path"])
    todo_path = home_path / "TODO.md"
    doc, fingerprint = _load_todo(todo_path)
    subject = str((read["mail"].get("metadata") or {}).get("subject") or message_id)
    linked_task, task_changed, created = _ensure_task(
        doc=doc, todo_path=todo_path, fingerprint=fingerprint, task_id=task_id,
        title=title or f"claim: {subject}", source_ref=_source_ref(message_id))
    marked = mark_input_read(
        home_ref=home, notice_id=notice["notice_id"],
        recipient_aliases=recipient_aliases)
    claimed = claim_notice(
        home_path=home_path, notice_id=notice["notice_id"],
        claimant_home_kind=home["home_kind"], claimant_home_id=home["home_id"],
        claimant_project_id=home["project_id"], task_ref=linked_task,
        action_ref=_source_ref(message_id), task_auto_created=created,
        claimant_aliases=recipient_aliases or set())
    return {
        "schema": "paos-mail-claim/v1", "message_id": message_id,
        "home": home, "mail": read["mail"], "notice": claimed,
        "read": marked.get("notice", {}), "task_id": linked_task,
        "task_changed": task_changed, "task_auto_created": created,
        "claim_changed": claimed.get("claim_changed"), "quiet": True,
    }


def _exact_waiting(value: str, task_id: str, message_id: str) -> bool:
    return value.strip() in {task_id, message_id, _source_ref(message_id)}


def result_mail(*, root: Path, project: dict[str, Any], agent_id: str,
                message_id: str, result: str, task_id: str = "",
                artifact_ref: str = "",
                recipient_aliases: set[str] | None = None) -> dict[str, Any]:
    resolution = normalize_notice_resolution(result)
    read = attention_read_project_mail_input(
        root=root, project=project, agent_id=agent_id, message_id=message_id,
        recipient_aliases=recipient_aliases)
    home = read["home"]
    notice = read["notice"]
    if not notice.get("claimed"):
        raise ValueError("Mail 尚未 claim，不能直接写 result")
    claimed_task = str(notice.get("claim_task_ref") or "")
    if task_id and task_id != claimed_task:
        raise ValueError(f"Result 只能写回接手 Task {claimed_task}")
    task_id = claimed_task
    if notice.get("state") == "handled":
        if (str(notice.get("resolution") or "") == resolution
                and str(notice.get("action_ref") or "") == task_id):
            doc, _ = _load_todo(Path(home["home_path"]) / "TODO.md")
            selected = next(
                (task for task in doc.get("tasks") or []
                 if task["id"] == task_id), {})
            return {
                "schema": "paos-mail-result/v1", "message_id": message_id,
                "home": home, "task_id": task_id,
                "task_state": selected.get("state", ""),
                "result": result, "notice": notice, "quiet": True,
                "replayed": True,
            }
        raise ValueError("Mail 已有不同处理结果，拒绝改写")
    home_path = Path(home["home_path"])
    todo_path = home_path / "TODO.md"
    doc, fingerprint = _load_todo(todo_path)
    selected = next(
        (task for task in doc.get("tasks") or [] if task["id"] == task_id), None)
    if selected is None:
        raise ValueError(f"接手 Task 不存在：{task_id}")
    auto_created = bool(notice.get("claim_task_auto_created"))
    changed = False
    waiting = str(doc["current"].get("waiting", "") or "")
    if auto_created:
        if selected.get("state") == "done":
            if selected.get("result") != result:
                raise ValueError("接手 Task 已有不同结果，拒绝改写")
        else:
            selected["state"] = "done"
            selected["result"] = result
            changed = True
    elif not selected.get("result"):
        # A broad existing Task is not auto-completed; only retain the step
        # result when it is still empty.
        selected["result"] = result
        changed = True
    if artifact_ref and selected.get("artifact_ref") != artifact_ref:
        selected["artifact_ref"] = artifact_ref
        changed = True
    if _exact_waiting(waiting, task_id, message_id):
        waiting = ""
        changed = True
    if changed:
        text = render_todo(
            home_kind=doc["home_kind"], home_id=doc["home_id"],
            project_id=doc["project_id"], pinned=doc.get("pinned", ""),
            objective=doc["current"]["objective"],
            next_action=doc["current"]["next_action"], waiting=waiting,
            inflight=doc["current"].get("inflight", ""),
            context_refs=doc["current"].get("context_refs", []),
            result_refs=doc["current"].get("result_refs", []),
            updated_at=doc["current"].get("updated_at", ""), tasks=doc["tasks"])
        write_todo(todo_path, text, expected_fingerprint=fingerprint)
    handled = attention_handle_mail_input(
        root=root, project=project, agent_id=agent_id, message_id=message_id,
        resolution=resolution, action_ref=task_id,
        recipient_aliases=recipient_aliases)
    return {
        "schema": "paos-mail-result/v1", "message_id": message_id,
        "home": home, "task_id": task_id,
        "task_state": selected.get("state"), "task_changed": changed,
        "result": result, "notice": handled.get("notice", {}), "quiet": True,
    }


def _rooter_notice(home: dict[str, Any], message_id: str) -> dict[str, Any]:
    identity = input_identity(
        home_kind="rooter", home_id=str(home["home_id"]), project_id="",
        source_kind="mail", source_ref=message_id)
    return read_notice(Path(home["home_path"]), notice_id_for(identity))


def claim_rooter_mail(*, home: dict[str, Any], message_id: str,
                      task_id: str = "", title: str = "") -> dict[str, Any]:
    home_path = Path(home["home_path"])
    mail_path = home_path / "mailbox" / f"{message_id}.md"
    if not mail_path.is_file():
        raise ValueError(f"Rooter Mail 不存在：{mail_path}")
    notice = _rooter_notice(home, message_id)
    if notice.get("state") == "handled":
        raise ValueError("Mail 已完结，不能再次接手")
    existing_task = str(notice.get("claim_task_ref") or "")
    if notice.get("claimed"):
        if task_id and task_id != existing_task:
            raise ValueError(f"Mail 已接手到 {existing_task}，不能改挂 {task_id}")
        marked = mark_input_read(home_ref=home, notice_id=notice["notice_id"])
        claimed = claim_notice(
            home_path=home_path, notice_id=notice["notice_id"],
            claimant_home_kind="rooter", claimant_home_id=str(home["home_id"]),
            claimant_project_id="", task_ref=existing_task,
            action_ref=_source_ref(message_id),
            task_auto_created=bool(notice.get("claim_task_auto_created")))
        return {
            "schema": "paos-mail-claim/v1", "message_id": message_id,
            "home": home, "notice": claimed, "read": marked.get("notice", {}),
            "task_id": existing_task, "task_changed": False,
            "claim_changed": False, "quiet": True,
        }
    todo_path = home_path / "TODO.md"
    doc, fingerprint = _load_todo(todo_path)
    linked_task, task_changed, created = _ensure_task(
        doc=doc, todo_path=todo_path, fingerprint=fingerprint, task_id=task_id,
        title=title or f"claim: {message_id}",
        source_ref=_source_ref(message_id))
    marked = mark_input_read(home_ref=home, notice_id=notice["notice_id"])
    claimed = claim_notice(
        home_path=home_path, notice_id=notice["notice_id"],
        claimant_home_kind="rooter", claimant_home_id=str(home["home_id"]),
        claimant_project_id="", task_ref=linked_task,
        action_ref=_source_ref(message_id), task_auto_created=created)
    return {
        "schema": "paos-mail-claim/v1", "message_id": message_id,
        "home": home, "notice": claimed, "read": marked.get("notice", {}),
        "task_id": linked_task, "task_changed": task_changed,
        "task_auto_created": created, "claim_changed": claimed.get("claim_changed"),
        "quiet": True,
    }


def result_rooter_mail(*, home: dict[str, Any], message_id: str, result: str,
                       task_id: str = "", artifact_ref: str = "") -> dict[str, Any]:
    resolution = normalize_notice_resolution(result)
    notice = _rooter_notice(home, message_id)
    if not notice.get("claimed"):
        raise ValueError("Rooter Mail 尚未 claim，不能直接写 result")
    claimed_task = str(notice.get("claim_task_ref") or "")
    if task_id and task_id != claimed_task:
        raise ValueError(f"Result 只能写回接手 Task {claimed_task}")
    task_id = claimed_task
    if notice.get("state") == "handled":
        if (str(notice.get("resolution") or "") == resolution
                and str(notice.get("action_ref") or "") == task_id):
            doc, _ = _load_todo(Path(home["home_path"]) / "TODO.md")
            selected = next(
                (task for task in doc.get("tasks") or []
                 if task["id"] == task_id), {})
            return {
                "schema": "paos-mail-result/v1", "message_id": message_id,
                "home": home, "task_id": task_id,
                "task_state": selected.get("state", ""),
                "result": result, "notice": notice, "quiet": True,
                "replayed": True,
            }
        raise ValueError("Rooter Mail 已有不同处理结果，拒绝改写")
    home_path = Path(home["home_path"])
    todo_path = home_path / "TODO.md"
    doc, fingerprint = _load_todo(todo_path)
    selected = next(
        (task for task in doc.get("tasks") or [] if task["id"] == task_id), None)
    if selected is None:
        raise ValueError(f"接手 Task 不存在：{task_id}")
    changed = False
    waiting = str(doc["current"].get("waiting", "") or "")
    if notice.get("claim_task_auto_created"):
        if selected.get("state") != "done":
            selected["state"] = "done"
            selected["result"] = result
            changed = True
        elif selected.get("result") != result:
            raise ValueError("接手 Task 已有不同结果，拒绝改写")
    elif not selected.get("result"):
        selected["result"] = result
        changed = True
    if artifact_ref and selected.get("artifact_ref") != artifact_ref:
        selected["artifact_ref"] = artifact_ref
        changed = True
    if _exact_waiting(waiting, task_id, message_id):
        waiting = ""
        changed = True
    if changed:
        text = render_todo(
            home_kind="rooter", home_id=doc["home_id"], project_id="",
            pinned=doc.get("pinned", ""), objective=doc["current"]["objective"],
            next_action=doc["current"]["next_action"], waiting=waiting,
            inflight=doc["current"].get("inflight", ""),
            context_refs=doc["current"].get("context_refs", []),
            result_refs=doc["current"].get("result_refs", []),
            updated_at=doc["current"].get("updated_at", ""), tasks=doc["tasks"])
        write_todo(todo_path, text, expected_fingerprint=fingerprint)
    handled = handle_notice(
        home_path=home_path, notice_id=notice["notice_id"],
        resolution=resolution, action_ref=task_id)
    return {
        "schema": "paos-mail-result/v1", "message_id": message_id,
        "home": home, "task_id": task_id, "task_state": selected.get("state"),
        "task_changed": changed, "result": result, "notice": handled,
        "quiet": True,
    }
