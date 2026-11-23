"""Read/activate a governed role through the same commands used by the presentation layer."""

from __future__ import annotations

import json
from urllib.parse import quote

from paos_attention_service import resolve_home_by_registry
from paos_human_action import confirm
from paos_installation import effective_data_root, load_installation_descriptor
from paos_stage import render, task_snapshot, with_refs
from paos_team import (
    PLAN,
    check_goal_originals,
    check_registered_handoffs,
    decision_subject,
    enroll,
    plan_view,
    propose,
    read_action,
    read_owner_acceptance,
    record_owner_acceptance,
    role_projection,
    team_path,
)
from paos_todo import write_todo


def add_team_parsers(sub):
    group = sub.add_parser(
        "team-plan", help="Plan, review and activate a team's temporary roles"
    ).add_subparsers(dest="plan_command", required=True)
    add_team_actions(group)
    group = sub.add_parser("task", help="Accept a finished goal with its evidence").add_subparsers(
        dest="task_command", required=True
    )
    accept = group.add_parser("accept")
    accept.add_argument("home")
    accept.add_argument("--task", required=True)
    accept.add_argument("--artifact", required=True)
    accept.add_argument("--basis", required=True)
    accept.add_argument("--remaining", required=True)
    accept.add_argument("--room")
    accept.add_argument("--read-to", type=int)
    accept.add_argument(
        "--carry",
        action="append",
        default=[],
        help="Existing waiting responsibility as HOME/TASK=continuation",
    )
    accept.add_argument("--cat-url", default="http://127.0.0.1:8870")


def add_team_actions(group):
    for name in ("propose", "plan", "members", "role", "enroll", "receipt", "confirm"):
        command = group.add_parser(name)
        command.add_argument("--cat-url", default="http://127.0.0.1:8870")
        if name in {"propose", "plan", "role", "enroll"}:
            command.add_argument("home")
        if name in {"propose", "plan", "enroll"}:
            command.add_argument("--task", required=name != "enroll", default="")
        if name == "propose":
            command.add_argument("--plan", required=True)
            command.add_argument("--member", action="append", required=True)
            command.add_argument("--close-policy", choices=["human_confirm", "owner"], default="owner")
        if name in {"members", "role", "enroll"}:
            command.add_argument("--room", required=True)
        if name == "role":
            command.add_argument("--duty", required=True)
            command.add_argument("--arrangement", required=True)
            command.add_argument("--deliverables", required=True)
            command.add_argument("--expected-revision", required=True, type=int)
        if name == "receipt":
            command.add_argument("receipt_id")
        if name == "confirm":
            command.add_argument(
                "action", choices=["open-plan", "approve-roles", "save-role", "accept-goal"]
            )
            command.add_argument("--id", required=True, dest="receipt_id")
            command.add_argument(
                "--input", required=True, help="JSON from the review interface, @file or stdin"
            )


def accept_task(home, staff, args, client, resolve, data):
    path, before, doc, task = task_snapshot(home, args.task)
    if any(r.startswith(PLAN) for r in task["source_refs"]) and not args.room:
        raise ValueError("此计划需关联已有专用房后验收")
    if task["state"] == "cancelled":
        raise ValueError("已取消的任务不能验收")
    note = "验收依据：" + args.basis + "。剩余事项：" + args.remaining
    accepted = task["state"] == "done"
    if accepted and (task["artifact_ref"] != args.artifact or task["result"] != note):
        raise ValueError("该任务已有不同验收结果")
    carried = {}
    for value in args.carry:
        item, sep, locator = value.partition("=")
        if not sep or not item.strip() or not locator.strip():
            raise ValueError("--carry 使用 HOME/TASK=接续原件")
        carried[item.strip()] = locator.strip()
    evidence = {
        "task": args.task,
        "artifact": args.artifact,
        "basis": args.basis,
        "remaining": args.remaining,
    }
    if carried:
        evidence["carried"] = carried
    team = None
    if args.room:
        evidence["read_to"] = args.read_to
        team = client.request("GET", team_path(args.room))["team"]
        if (team["plan"]["owner"], team["plan"]["task"], team["plan"]["project"]) != (
            staff,
            args.task,
            home["project_id"],
        ):
            raise ValueError("此专用房属于其他目标")
        if team["accepted"] is not None and team["accepted"] != evidence:
            raise ValueError("该房已按不同的依据验收")
        if team["accepted"] is None and team["plan"]["close_policy"] == "human_confirm":
            raise ValueError("此目标需先在 Human 入口完成同一项验收")
    if not accepted and (team is None or team["accepted"] is None):
        check_goal_originals(home, staff, doc, task, evidence)
    if not accepted:
        task.update(state="done", result=note, artifact_ref=args.artifact, waiting="")
        task["acceptance_refs"] = with_refs(task["acceptance_refs"], [args.basis, *carried.values()])
        candidate = render(doc)
    if team is not None and team["accepted"] is None:
        if team["plan"]["version"] != plan_view(home, staff, task)["plan"]["version"]:
            raise ValueError("验收时计划范围已变化")
        if not team["roles_receipt"] or not all(role["approved"] for role in team["roles"].values()):
            raise ValueError("验收前须完成约定角色放行")
        if args.read_to is None:
            raise ValueError("专用房验收需要实际已读的 --read-to")
        check_registered_handoffs(team["plan"]["members"], args.room, resolve, carried)
        receipt = record_owner_acceptance(data, args.room, team, evidence)
        client.request("POST", team_path(args.room) + "/accept", {"receipt_id": receipt})
    if not accepted:
        write_todo(path, candidate, expected_fingerprint=before)
    return {
        "ok": True,
        "task_id": args.task,
        "state": "done",
        "replayed": accepted,
        "artifact": args.artifact,
    }


def execute_team_actions(args, installation, identity, cat_client, text_arg):
    data = effective_data_root(load_installation_descriptor(installation))

    def resolve(h):
        return resolve_home_by_registry(h, installation_file=str(installation))

    client = cat_client(args.cat_url, service="CAT")
    op = "accept" if args.command == "task" else args.plan_command
    if op == "receipt":
        if args.receipt_id.startswith("oa-"):
            return {"ok": True, "receipt": read_owner_acceptance(data, args.receipt_id, resolve)}
        proof = read_action(data, args.receipt_id)
        if proof["action"] == "open-plan":
            current, _ = decision_subject("open-plan", proof["input"], resolve, client)
            if current != proof["subject"]:
                raise ValueError("Human 已查看的计划版本发生变化")
        return {"ok": True, "receipt": proof}
    if op == "confirm":
        request = json.loads(text_arg(args.input, "Human action", required=True))
        if not isinstance(request, dict):
            raise ValueError("Human 操作需要明确的对象")
        return confirm(data, args.action, args.receipt_id, request, resolve, client)
    if op == "members":
        team = client.request("GET", team_path(args.room))["team"]
        return role_projection(team, args.room, resolve)
    home = resolve(args.home)
    staff = identity(args.home, installation_path=installation)["staff_number"] or args.home
    if op == "accept":
        return accept_task(home, staff, args, client, resolve, data)
    if op == "role":
        role = {k: getattr(args, k) for k in ("duty", "arrangement", "deliverables")}
        return client.request(
            "POST",
            team_path(args.room) + "/roles/" + quote(staff, safe=""),
            {"actor_id": staff, "expected_revision": args.expected_revision, "role": role},
        )
    if op == "enroll":
        return enroll(home, staff, args.room, args.task, client, resolve)
    if op == "propose":
        members = [
            identity(m, installation_path=installation)["staff_number"] or m for m in args.member
        ]
        return propose(home, staff, args.task, args.plan, members, args.close_policy)
    _, _, _, task = task_snapshot(home, args.task)
    return {"ok": True, **plan_view(home, staff, task)}
