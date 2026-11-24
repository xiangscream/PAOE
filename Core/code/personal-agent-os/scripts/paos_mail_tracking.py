"""Project the original recipient receipts onto the sender's existing Task."""
from __future__ import annotations

import hashlib
from pathlib import Path

from paos_attention_service import AttentionServiceProblem, read_history_input, read_source_status
from paos_mail import MailProblem, dispatch_status
from paos_todo import parse_todo, render_todo, write_todo


def handoff_status(root, message_id, resolve_home, installation_file=None):
    dispatch = dispatch_status(root, message_id, registry_lookup=resolve_home,
                               installation_path=installation_file)
    if resolve_home is None:
        return dispatch
    for delivery in dispatch["deliveries"]:
        recipient = delivery["recipient_agent_id"]
        notice = None
        if delivery["state"] == "delivered":
            try:
                notice = read_source_status(
                    home_ref=resolve_home(recipient), source_kind="mail", source_ref=message_id,
                    installation_file=installation_file,
                )["notice"]
            except AttentionServiceProblem as problem:
                if problem.code not in {"notice_missing", "attention_home_not_v4"}:
                    raise
        elif delivery["state"] == "archived":
            notice = read_history_input(
                history_root=delivery["history_root"], agent_id=recipient, message_id=message_id,
            ).get("notice")
        handling = {"state": "unobserved"}
        if notice is not None:
            handling = {
                "state": "resolved" if notice["state"] == "handled" else
                         "claimed" if notice.get("claimed") else "awaiting_claim",
                "notice_id": notice["notice_id"],
                "claimed_by": notice.get("claimed_by_home_id", ""),
                "task_id": notice.get("claim_task_ref", ""),
                "result": notice["resolution"],
                "action_ref": notice["action_ref"],
            }
        delivery["handoff"] = handling
    return dispatch


def _task_snapshot(home, task_id):
    path = Path(home["home_path"]) / "TODO.md"
    raw = path.read_bytes()
    todo = parse_todo(raw.decode("utf-8-sig"))
    task = next((item for item in todo["tasks"] if item["id"] == task_id), None)
    if task is None:
        raise MailProblem("mail_sender_task_missing", f"当前工位没有 Task {task_id}。")
    return path, raw, todo, task


def _confirm_sender(dispatch, home, resolve_home):
    if dispatch["sender_kind"] != "agent" or not dispatch["sender_id"]:
        raise MailProblem("mail_sender_mismatch", "只能关联由本工位发出的 Agent Mail。")
    author = resolve_home(dispatch["sender_id"])
    if (author["home_kind"], author["home_id"], author["project_id"]) != (
            home["home_kind"], home["home_id"], home["project_id"]):
        raise MailProblem("mail_sender_mismatch", "只能关联由本工位发出的 Agent Mail。")


def track_sent_mail(root, project_id, message_id, home, task_id, resolve_home,
                    installation_file=None):
    dispatch = handoff_status(root, message_id, resolve_home, installation_file)
    _confirm_sender(dispatch, home, resolve_home)
    path, raw, todo, task = _task_snapshot(home, task_id)
    ref = f"sent-mail:{project_id}:{message_id}"
    changed = ref not in task["source_refs"]
    if changed:
        task["source_refs"].append(ref)
        body = render_todo(
            home_kind=todo["home_kind"], home_id=todo["home_id"], project_id=todo["project_id"],
            pinned=todo["pinned"], tasks=todo["tasks"], **todo["current"],
        )
        write_todo(path, body, expected_fingerprint=hashlib.sha256(raw).hexdigest())
    return {"task_id": task_id, "source_ref": ref, "linked": True,
            "changed": changed, "dispatch": dispatch}


def sent_task_status(root, project_id, home, task_id, resolve_home, installation_file=None):
    _, _, _, task = _task_snapshot(home, task_id)
    prefix = f"sent-mail:{project_id}:"
    dispatches = []
    waiting = []
    for ref in task["source_refs"]:
        if not ref.startswith(prefix):
            continue
        dispatch = handoff_status(root, ref[len(prefix):], resolve_home, installation_file)
        _confirm_sender(dispatch, home, resolve_home)
        dispatches.append(dispatch)
        for delivery in dispatch["deliveries"]:
            if delivery["handoff"]["state"] != "resolved":
                waiting.append({
                    "message_id": dispatch["message_id"], "subject": dispatch["subject"],
                    "recipient": delivery["recipient_agent_id"], "state": delivery["handoff"]["state"],
                })
    return {"task": task, "mail": dispatches, "mail_waiting": waiting}
