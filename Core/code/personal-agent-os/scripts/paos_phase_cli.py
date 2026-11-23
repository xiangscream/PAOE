"""Command contracts shared by the four user-facing Harness adapters."""

from paos_attention_service import resolve_home_by_registry
from paos_content import consume, list_changes
from paos_context import read_context
from paos_context_search import add_search_parser, collection_plan, search_context
from paos_installation import effective_data_root, load_installation_descriptor
from paos_phase_stop import on_stop
from paos_stage import deliver
from paos_stage import task_snapshot
from paos_team import ROLE, live_role


def add_phase_parsers(sub):
    ctx = sub.add_parser(
        "context", help="Read phase inputs or end native participation"
    ).add_subparsers(dest="context_command", required=True)
    add_search_parser(ctx)
    read = ctx.add_parser("read", help="Read original phase inputs from the registered Home")
    read.add_argument("home")
    read.add_argument("--task", default="")
    read.add_argument(
        "--reason", choices=["startup", "resume", "compact", "stage", "request"], default="resume"
    )
    read.add_argument(
        "--source", action="append", default=[], help="Required local text source (repeatable)"
    )
    read.add_argument("--cat-url", help="CAT endpoint for a governed role in this Task")
    stop = ctx.add_parser("stop", help="End room presence and decide on one continuation")
    stop.add_argument("home")
    stop.add_argument("--event", required=True)
    stop.add_argument("--task", default="")
    stop.add_argument("--interrupted", action="store_true")
    stop.add_argument("--reentry", action="store_true")
    stop.add_argument("--waiting-human", action="store_true")
    stop.add_argument("--cat-url", help="The CAT endpoint explicitly selected for this installation")

    stage = sub.add_parser("stage", help="Deliver work on an existing Task").add_subparsers(
        dest="stage_command", required=True
    )
    send = stage.add_parser("deliver", help="Save a stage result and its sources")
    send.add_argument("home")
    send.add_argument("--task", required=True)
    send.add_argument("--id", required=True, dest="operation", help="Stable delivery ID")
    send.add_argument("--artifact", action="append", required=True)
    send.add_argument("--intent", action="append", required=True)
    send.add_argument("--result", required=True)
    send.add_argument("--current", action="store_true", help="Make this Task the Home's current focus")
    send.add_argument("--cat-url", help="CAT endpoint for a governed role in this Task")
    next_step = send.add_mutually_exclusive_group(required=True)
    next_step.add_argument("--next", dest="next_action", default="")
    next_step.add_argument("--waiting", default="")

    content = sub.add_parser(
        "content", help="Read and consume versions of changed originals"
    ).add_subparsers(dest="content_command", required=True)
    changes = content.add_parser("changes", help="Read changes after a sequence number")
    changes.add_argument("--after", type=int, default=0)
    changes.add_argument("--limit", type=int, default=50)
    done = content.add_parser("consume", help="Record the actual result of processing changes")
    done.add_argument("home")
    done.add_argument("--through", type=int, required=True)
    done.add_argument("--result-ref", required=True)


def execute_phase(args, installation, identity, cat_client):
    descriptor = load_installation_descriptor(installation)
    data = effective_data_root(descriptor)
    if args.command == "content" and args.content_command == "changes":
        return list_changes(data, args.after, args.limit)
    home = resolve_home_by_registry(args.home, installation_file=str(installation))
    if args.command == "context" and args.context_command == "collections":
        return collection_plan(home, installation, descriptor, args.project)
    if args.command == "context" and args.context_command == "search":
        return search_context(args, home, installation, descriptor)
    if args.command == "content":
        return consume(data, home, args.through, args.result_ref)
    staff = identity(args.home, installation_path=installation).get("staff_number") or args.home
    if args.command == "context" and args.context_command == "stop":
        return on_stop(
            data,
            home,
            staff=staff,
            event=args.event,
            task_id=args.task,
            interrupted=args.interrupted,
            reentry=args.reentry,
            waiting_human=args.waiting_human,
            client=cat_client(args.cat_url, service="CAT") if args.cat_url else None,
        )

    def phase():
        result = read_context(
            home,
            staff_number=staff,
            reason=getattr(args, "reason", "stage"),
            task_id=args.task,
            sources=getattr(args, "source", ()),
        )
        if not result["task_id"] or not any(d["kind"] == "task" for d in result["documents"]):
            return result
        _, _, _, task = task_snapshot(home, result["task_id"])
        for ref in task["source_refs"]:
            if ref.startswith(ROLE):
                if not args.cat_url:
                    result["missing"].append(
                        {"kind": "active_role", "path": ref, "reason": "cat_url_required"}
                    )
                    continue
                client = cat_client(args.cat_url, service="CAT")
                try:
                    team, role = live_role(
                        client,
                        ref[len(ROLE) :],
                        staff,
                        lambda h: resolve_home_by_registry(h, installation_file=str(installation)),
                    )
                except ValueError as exc:
                    result["missing"].append({"kind": "active_role", "path": ref, "reason": str(exc)})
                else:
                    result["documents"].append(
                        {
                            "kind": "active_role",
                            "path": ref,
                            "version": str(role["revision"]),
                            "plan_version": team["plan"]["version"],
                            "roles_receipt": team["roles_receipt"],
                            "body": "\n".join(
                                role["role"][k] for k in ("duty", "arrangement", "deliverables")
                            )
                            + "\n"
                            + team["roles_receipt"],
                        }
                    )
        result["ok"] = not result["missing"]
        return result

    if args.command == "context":
        return phase()
    checked = phase()
    if not checked["ok"]:
        return {"ok": False, "error_code": "stage_context_incomplete", "context": checked}
    received = deliver(
        data,
        home,
        task_id=args.task,
        operation=args.operation,
        artifacts=args.artifact,
        intents=args.intent,
        result=args.result,
        next_action=args.next_action,
        waiting=args.waiting,
        current=args.current,
    )
    received["context"] = phase()
    return received
