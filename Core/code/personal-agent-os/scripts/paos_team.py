"""Team plans link an owner's Markdown to an existing Task. CAT owns temporary role drafts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from urllib.parse import quote

from paos_content import original_version, pack, scoped_file
from paos_context import _section, local_source
from paos_stage import render, task_snapshot
from paos_todo import parse_todo, read_todo, write_todo

PLAN = "team-plan:"
SEAT = "team-member:"
REVIEW = "team-review:"
ROLE = "cat-role:"


def _values(task, prefix):
    return [s[len(prefix) :] for s in task["source_refs"] if s.startswith(prefix)]


def _plan_text(home, locator):
    root = Path(home["project_root"] or home["home_path"])
    name, _, section = locator.partition("#")
    path = scoped_file(root, name)
    if path.suffix.lower() != ".md":
        raise ValueError("计划需要项目内的 Markdown 原件")
    text = path.read_text(encoding="utf-8-sig")
    if section:
        text = _section(text, "## " + section)
    if not text.strip():
        raise ValueError("计划原文或选择的章节为空")
    return text


def plan_view(home, staff, task):
    plans, roster = _values(task, PLAN), _values(task, SEAT)
    policies = _values(task, REVIEW)
    if len(plans) != 1 or staff not in roster or len(policies) != 1:
        raise ValueError("此任务还没有完整团队计划")
    body = _plan_text(home, plans[0])
    scope = {
        "owner": staff,
        "project": home["project_id"],
        "task": task["id"],
        "title": task["title"],
        "path": plans[0],
        "members": roster,
        "close_policy": policies[0],
    }
    scope["content_version"] = hashlib.sha256(
        pack([scope["title"], scope["path"], scope["close_policy"], body]).encode("utf-8")
    ).hexdigest()
    # The actual plan text and roster are the subject the Human approves.
    scope["version"] = hashlib.sha256(pack([scope, body]).encode("utf-8")).hexdigest()
    return {"plan": scope, "body": body}


def propose(home, staff, task_id, locator, members, policy):
    todo, before, doc, task = task_snapshot(home, task_id)
    if task["state"] in {"done", "cancelled"}:
        raise ValueError("已结束的任务不能发起团队计划")
    if staff not in members:
        raise ValueError("计划需要在团队中的负责人")
    task["source_refs"] = [
        ref for ref in task["source_refs"] if not ref.startswith((PLAN, SEAT, REVIEW))
    ]
    task["source_refs"] += [
        PLAN + locator,
        *(SEAT + s for s in dict.fromkeys(members)),
        REVIEW + policy,
    ]
    view = plan_view(home, staff, task)
    new = render(doc)
    if new != todo.read_text(encoding="utf-8-sig"):
        write_todo(todo, new, expected_fingerprint=before)
    return {"ok": True, **view}


def receipt_path(data, ident):
    if not isinstance(ident, str) or not re.fullmatch(r"ha-[0-9a-f]{32}", ident):
        raise ValueError("Human 确认记录 ID 无效")
    return data / "human-actions" / (ident + ".json")


def read_action(data, ident):
    path = receipt_path(data, ident)
    proof = json.loads(path.read_text(encoding="utf-8"))
    if (
        proof.get("schema") != "paoe-human-action/v1"
        or proof.get("id") != ident
        or proof.get("channel") != "native-human-confirmation"
        or not isinstance(proof.get("subject"), dict)
    ):
        raise ValueError("Human 确认记录不完整")
    return proof


def publish_receipt(path, receipt):
    """Create a fully written immutable action record without replacing concurrent evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        os.link(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def acceptance_versions(home, evidence, *, archived=None):
    """Bind only the two reviewed originals. A completed receipt can outlive its files."""
    root = Path(home["project_root"] or home["home_path"]).resolve()
    versions = {}
    for key in ("artifact", "basis"):
        path = local_source(root, evidence[key])
        if path is None or not path.is_relative_to(root):
            raise ValueError(f"验收原件超出项目范围：{evidence[key]}")
        try:
            versions[key] = original_version(path)
        except FileNotFoundError as error:
            if archived is None:
                raise ValueError(f"所选项目原件不可读：{evidence[key]}") from error
            versions[key] = archived[key]
    return versions


def record_owner_acceptance(data, room, team, acceptance, home):
    acceptance = {**acceptance, "versions": acceptance_versions(home, acceptance)}
    subject = {
        "room": room,
        "owner": team["plan"]["owner"],
        "version": team["plan"]["version"],
        "revision": team["revision"],
        "roles_receipt": team["roles_receipt"],
        "acceptance": acceptance,
    }
    ident = "oa-" + hashlib.sha256(pack(subject).encode("utf-8")).hexdigest()[:32]
    record = {"id": ident, "action": "owner-accept", "subject": subject}
    path = data / "owner-acceptances" / (ident + ".json")
    try:
        publish_receipt(path, record)
    except FileExistsError:
        if json.loads(path.read_text(encoding="utf-8")) != record:
            raise ValueError("验收回执与已有记录不符")
    return ident


def team_path(room):
    return "/api/rooms/" + quote(room, safe="") + "/team"


def live_role(client, room, staff, resolve_home):
    team = client.request("GET", team_path(room))["team"]
    plan = team["plan"]
    owner_home = resolve_home(plan["owner"])
    _, _, _, owner_task = task_snapshot(owner_home, plan["task"])
    actual = plan_view(owner_home, plan["owner"], owner_task)["plan"]
    if actual["version"] != plan["version"] and (
        actual["content_version"] != plan.get("content_version") or staff not in actual["members"]
    ):
        raise ValueError("团队计划范围发生变化，需要 Human 确认受影响安排")
    role = team["roles"].get(staff)
    if team["accepted"] or not team["roles_receipt"] or not role or not role["approved"]:
        raise ValueError("本房角色尚未获准执行或目标已验收")
    return team, role


def enroll(home, staff, room, task_id, client, resolve_home):
    team, role = live_role(client, room, staff, resolve_home)
    anchor = ROLE + room
    path = Path(home["home_path"]) / "TODO.md"
    raw = path.read_bytes()
    doc = parse_todo(raw.decode("utf-8-sig"))
    if (doc["home_id"], doc["home_kind"], doc["project_id"]) != (
        home["home_id"],
        home["home_kind"],
        home["project_id"],
    ):
        raise ValueError("工位 TODO 身份不符")
    matches = [t for t in doc["tasks"] if anchor in t["source_refs"]]
    if len(matches) > 1 or (matches and task_id and matches[0]["id"] != task_id):
        raise ValueError("本人已有任务关联这个角色")
    if matches:
        task = matches[0]
    elif task_id:
        task = next((t for t in doc["tasks"] if t["id"] == task_id), None)
        if task is None:
            raise ValueError("--task 需要本人已有任务；省略以接入新任务")
    else:
        ident = "T-" + room
        if any(t["id"] == ident for t in doc["tasks"]):
            raise ValueError("生成的任务 ID 已用于其他责任")
        task = {"id": ident, "title": team["plan"]["title"], "state": "todo", "source_refs": []}
        doc["tasks"].append(task)
    if task["state"] in {"done", "cancelled"}:
        raise ValueError("已结束的任务不能接入角色")
    if anchor not in task["source_refs"]:
        task["source_refs"].append(anchor)
        write_todo(path, render(doc), expected_fingerprint=hashlib.sha256(raw).hexdigest())
    return {"ok": True, "room": room, "task_id": task["id"], "role": role, "claimed": True}


def linked_tasks(members, room, resolve_home):
    for staff in members:
        home = resolve_home(staff)
        todo = read_todo(Path(home["home_path"]) / "TODO.md")
        task = next((t for t in todo["tasks"] if ROLE + room in t["source_refs"]), None)
        current = (
            todo["current"]
            if task and "task:" + task["id"] in todo["current"]["context_refs"]
            else None
        )
        yield staff, task, current


def role_projection(team, room, resolve_home):
    cards = {
        staff: {"role": team["roles"].get(staff), "task": task, "current": current}
        for staff, task, current in linked_tasks(team["plan"]["members"], room, resolve_home)
    }
    return {"ok": True, "room": room, "team": team, "cards": cards}


def check_registered_handoffs(members, room, resolve_home, carried):
    for staff, task, current in linked_tasks(members, room, resolve_home):
        current = current or {}
        if task and (task["waiting"] or current.get("waiting") or current.get("inflight")):
            target = staff + "/" + task["id"]
            if not str(carried.get(target) or "").strip():
                raise ValueError("该目标仍登记在途或等待，请给出实际去向：" + target)


def check_goal_originals(home, owner, doc, task, evidence):
    root = Path(home["project_root"] or home["home_path"])
    for key in ("artifact", "basis"):
        scoped_file(root, evidence[key])
    if not str(evidence.get("remaining") or "").strip():
        raise ValueError("请说明剩余事项的去向")
    carried = evidence.get("carried", {})
    if not isinstance(carried, dict) or not all(
        isinstance(v, str) and v.strip() for v in carried.values()
    ):
        raise ValueError("剩余责任需要员工/任务及接续入口")
    current = doc["current"] if "task:" + task["id"] in doc["current"]["context_refs"] else {}
    if task["waiting"] or current.get("waiting") or current.get("inflight"):
        if owner + "/" + task["id"] not in carried:
            raise ValueError("本目标还有已登记的等待或在途事项，请先记录其实际去向")


def read_owner_acceptance(data, ident, resolve_home=None):
    """History is immutable; first application also verifies the originals at the registered Home."""
    if not re.fullmatch(r"oa-[0-9a-f]{32}", ident):
        raise ValueError("验收回执 ID 无效")
    record = json.loads((data / "owner-acceptances" / (ident + ".json")).read_text(encoding="utf-8"))
    if record.get("id") != ident or record.get("action") != "owner-accept":
        raise ValueError("验收回执与原操作不符")
    if resolve_home:
        subject = record["subject"]
        verify_goal(subject, subject["acceptance"], resolve_home, "owner")
    return record


def verify_goal(subject, evidence, resolve_home, policy):
    home = resolve_home(subject["owner"])
    _, _, doc, task = task_snapshot(home, evidence["task"])
    plan = plan_view(home, subject["owner"], task)["plan"]
    if (
        plan["version"] != subject["version"]
        or plan["close_policy"] != policy
        or task["state"] == "cancelled"
    ):
        raise ValueError("验收目标或约定验收人已变化")
    check_goal_originals(home, subject["owner"], doc, task, evidence)
    if acceptance_versions(home, evidence) != evidence.get("versions"):
        raise ValueError("验收成果或依据的内容版本已经变化，请复核原件")
    check_registered_handoffs(
        plan["members"], subject["room"], resolve_home, evidence.get("carried", {})
    )


def decision_subject(action, payload, resolve_home, client):
    """Construct the exact subject displayed by the Human client from authoritative originals."""
    if action == "open-plan":
        staff = payload["owner"]
        home = resolve_home(staff)
        _, _, _, task = task_snapshot(home, payload["task"])
        if task["state"] in {"done", "cancelled"}:
            raise ValueError("该计划任务已结束")
        view = plan_view(home, staff, task)
        if payload.get("version") != view["plan"]["version"]:
            raise ValueError("计划已变化，请读取最新原件")
        subject = dict(view["plan"])
        if "affected_members" in payload:
            affected = payload["affected_members"]
            if not isinstance(affected, list) or not all(s in subject["members"] for s in affected):
                raise ValueError("受影响成员应从计划参与者中选择")
            subject["affected_members"] = list(dict.fromkeys(affected))
        return subject, view["body"]
    if action not in {"approve-roles", "save-role", "accept-goal"}:
        raise ValueError("未登记的 Human 操作")
    room = payload["room"]
    team = client.request("GET", team_path(room))["team"]
    current = resolve_home(team["plan"]["owner"])
    _, _, owner_doc, owner_task = task_snapshot(current, team["plan"]["task"])
    if (
        plan_view(current, team["plan"]["owner"], owner_task)["plan"]["version"]
        != team["plan"]["version"]
    ):
        raise ValueError("当前房间关联的计划已改变")
    if action == "approve-roles":
        if payload.get("expected_revision") != team["revision"] or set(team["roles"]) != set(
            team["plan"]["members"]
        ):
            raise ValueError("角色尚未齐备或已变化")
        return {"room": room, "expected_revision": team["revision"]}, pack(team["roles"])
    if action == "save-role":
        home = payload["home"]
        old = team["roles"].get(home, {})
        if home not in team["plan"]["members"] or payload.get("expected_revision") != old.get(
            "revision", 0
        ):
            raise ValueError("该角色不属于本房或已变化")
        values = {k: payload["role"][k] for k in ("duty", "arrangement", "deliverables")}
        if not all(isinstance(v, str) and v.strip() for v in values.values()):
            raise ValueError("请填写职责、安排与交付物")
        return {
            "room": room,
            "home": home,
            "expected_revision": old.get("revision", 0),
            "role": values,
        }, pack(values)
    if team["plan"]["close_policy"] != "human_confirm" or payload.get("task") != team["plan"]["task"]:
        raise ValueError("正式验收人与原计划不匹配")
    check_goal_originals(current, team["plan"]["owner"], owner_doc, owner_task, payload)
    carried = payload.get("carried", {})
    check_registered_handoffs(team["plan"]["members"], room, resolve_home, carried)
    subject = {k: payload[k] for k in ("room", "task", "artifact", "basis", "remaining", "read_to")}
    subject.update(
        owner=team["plan"]["owner"],
        version=team["plan"]["version"],
        revision=team["revision"],
        roles_receipt=team["roles_receipt"],
        versions=acceptance_versions(current, payload),
    )
    if carried:
        subject["carried"] = carried
    return subject, pack(subject)
