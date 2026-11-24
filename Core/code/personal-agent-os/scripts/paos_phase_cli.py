"""Command contracts shared by the four user-facing Harness adapters."""

import os
from pathlib import Path

from paos_attention_service import resolve_home_by_registry
from paos_cat_activation import CatActivationProblem
from paos_content import consume, consumer_progress, list_changes, read_change
from paos_content_watch_cli import add_watch_parser, execute_watch
from paos_context import read_context
from paos_context_search import add_search_parser, collection_plan, search_context
from paos_installation import effective_data_root, load_installation_descriptor
from paos_phase_stop import on_stop
from paos_stage import deliver
from paos_stage import task_snapshot
from paos_registry import ProjectRegistry
from paos_relations import related
from paos_exm_publish import add_originals_parser, execute_originals
from paos_team import ROLE, live_role

DEFAULT_CAT_URL = "http://127.0.0.1:8870"


def _default_cat_url() -> str:
    return (os.environ.get("CAT_BASE_URL") or DEFAULT_CAT_URL).rstrip("/")


def add_phase_parsers(sub):
    ctx = sub.add_parser(
        "context", help="Read phase inputs or end native participation"
    ).add_subparsers(dest="context_command", required=True)
    add_search_parser(ctx)
    add_originals_parser(ctx)
    relations = ctx.add_parser("related", help="Expand explicit topic links and derived backlinks")
    relations.add_argument("home")
    relations.add_argument("--source", required=True)
    relations.add_argument("--project", help="Registered project containing the topic notes")
    relations.add_argument("--depth", type=int, default=1)
    relations.add_argument("--limit", type=int, default=8, help="Maximum returned nodes")
    read = ctx.add_parser("read", help="Read original phase inputs from the registered Home")
    read.add_argument("home")
    read.add_argument("--task", default="")
    read.add_argument(
        "--reason", choices=["startup", "resume", "compact", "stage", "request"], default="resume"
    )
    read.add_argument(
        "--source", action="append", default=[], help="Required local text source (repeatable)"
    )
    read.add_argument(
        "--cat-url",
        default=_default_cat_url(),
        help="CAT endpoint for a governed role in this Task; default CAT_BASE_URL or "
             "http://127.0.0.1:8870",
    )
    stop = ctx.add_parser("stop", help="End room presence and decide on one continuation")
    stop.add_argument("home")
    stop.add_argument("--event", required=True)
    stop.add_argument("--task", default="")
    stop.add_argument("--interrupted", action="store_true")
    stop.add_argument("--reentry", action="store_true")
    stop.add_argument("--waiting-human", action="store_true")
    stop.add_argument("--presence-only", action="store_true",
                      help="Leave active rooms without continuing or claiming a task")
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
    send.add_argument(
        "--cat-url",
        default=_default_cat_url(),
        help="CAT endpoint for a governed role in this Task; default CAT_BASE_URL or "
             "http://127.0.0.1:8870",
    )
    next_step = send.add_mutually_exclusive_group(required=True)
    next_step.add_argument("--next", dest="next_action", default="")
    next_step.add_argument("--waiting", default="")

    content = sub.add_parser(
        "content", help="Read and consume versions of changed originals"
    ).add_subparsers(dest="content_command", required=True)
    add_watch_parser(content)
    changes = content.add_parser("changes", help="Read changes after a sequence number")
    changes.add_argument("--after", type=int, default=None)
    changes.add_argument("--home", help="Resume from this Home's committed consumption cursor")
    changes.add_argument("--limit", type=int, default=50)
    show = content.add_parser("show", help="Read captured before/after text; old gaps remain explicit")
    show.add_argument("seq", type=int)
    status = content.add_parser("status", help="Read a consumer's saved cursor and pending count")
    status.add_argument("home")
    done = content.add_parser("consume", help="Record the actual result of processing changes")
    done.add_argument("home")
    done.add_argument("--through", type=int, required=True)
    done.add_argument("--result-ref", required=True)


def _context_sources(context):
    return [
        {key: value for key, value in document.items() if key != "body"}
        for document in context.get("documents", [])
        if isinstance(document, dict)
    ]


def _stage_failure(context, args):
    """Keep the normal failure receipt small; full text stays explicit."""
    sources = _context_sources(context)
    compact = {**context, "documents": sources}
    cat_url = str(getattr(args, "cat_url", "") or "").strip()
    hint = (
        f"paos context read {args.home} --task {args.task} --reason stage"
        + (f" --cat-url {cat_url}" if cat_url else "")
    )
    return {
        "ok": False,
        "error_code": "stage_context_incomplete",
        "missing": compact["missing"],
        "sources": sources,
        "read_hint": hint,
        "context": context if getattr(args, "full_result", False) else compact,
    }


def execute_phase(args, installation, identity, cat_client):
    descriptor = load_installation_descriptor(installation)
    data = effective_data_root(descriptor)
    if args.command == "context" and args.context_command == "originals":
        return execute_originals(args, installation)
    if args.command == "content" and args.content_command == "watch":
        return execute_watch(args, installation)
    if args.command == "content" and args.content_command == "changes":
        after = args.after
        if after is None and args.home:
            target = resolve_home_by_registry(args.home, installation_file=str(installation))
            after = consumer_progress(data, target["home_id"])["cursor"]
        return list_changes(data, after or 0, args.limit)
    if args.command == "content" and args.content_command == "show":
        return read_change(data, args.seq)
    home = resolve_home_by_registry(args.home, installation_file=str(installation))
    if args.command == "context" and args.context_command == "related":
        project = args.project or home["project_id"]
        if not project:
            raise ValueError("安装级工位展开主题时需用 --project 指定登记项目")
        root = ProjectRegistry(installation).read_record(project)["root_path"]
        return related(root, args.source, source_roots=_project_roots(installation, data),
                       depth=args.depth, limit=args.limit)
    if args.command == "context" and args.context_command == "collections":
        return collection_plan(home, installation, descriptor, args.project)
    if args.command == "context" and args.context_command == "search":
        return search_context(args, home, installation, descriptor)
    if args.command == "content":
        if args.content_command == "status":
            return consumer_progress(data, home["home_id"])
        return consume(data, home, args.through, args.result_ref,
                       source_roots=_project_roots(installation, data))
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
            presence_only=args.presence_only,
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
        cat_url = str(getattr(args, "cat_url", "") or _default_cat_url()).rstrip("/")
        for ref in task["source_refs"]:
            if ref.startswith(ROLE):
                try:
                    client = cat_client(cat_url, service="CAT")
                    team, role = live_role(
                        client,
                        ref[len(ROLE) :],
                        staff,
                        lambda h: resolve_home_by_registry(h, installation_file=str(installation)),
                    )
                except CatActivationProblem as exc:
                    result["missing"].append(
                        {"kind": "active_role", "path": ref, "reason": exc.code}
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
        return _stage_failure(checked, args)
    return deliver(
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
        source_roots=_project_roots(installation, data),
    )


def _project_roots(installation, data):
    """Cross-project originals come from explicit registry entries, not neighboring folders."""
    registry = ProjectRegistry(installation)
    return [registry.read_record(p.stem)["root_path"]
            for p in sorted((Path(data) / "project-registry/projects").glob("*.json"))]
