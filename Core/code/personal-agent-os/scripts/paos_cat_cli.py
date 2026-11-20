"""Parse explicit CAT requests into the independent CAT transport.

Learning note: CLI parsing and remote requests are separated. Ordinary
Project/Home/TODO operations never need a running CAT server; this adapter
gets used only when the user explicitly requests a CAT command.
"""
from urllib.parse import quote, urlencode


def add_cat_parser(sub):
    cat = sub.add_parser("cat", help="System roundtable; no Project or Work required")
    cat.add_argument("--url", default="http://127.0.0.1:8870", help="CAT origin, separate from PAOS")
    commands = cat.add_subparsers(dest="cat_command", required=True)
    listing = commands.add_parser("list", help="List roundtables or one member's rooms and unread positions")
    listing.add_argument("--home", help="Read this member's room recovery view")
    create = commands.add_parser("create", help="Create a roundtable")
    create.add_argument("--title", required=True)
    create.add_argument("--from", dest="actor_id")
    create.add_argument("--owner", dest="owner_id")
    create.add_argument("--close-policy", choices=["human_confirm", "owner"])
    _context_arguments(create)
    for name, help_text in (("show", "Show a roundtable"), ("members", "List roundtable members"),
                            ("close", "Close a roundtable; history stays readable")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("room_id")
        if name == "close":
            command.add_argument("--from", dest="actor_id")
            command.add_argument("--action", choices=["request", "confirm", "continue"], default="request")
    context = commands.add_parser("context", help="Update a room's existing task/INDEX references")
    context.add_argument("room_id")
    context.add_argument("--from", dest="actor_id", required=True)
    context.add_argument("--owner", dest="owner_id")
    _context_arguments(context)
    progress = commands.add_parser("progress", help="Record the member's room presence and actual read position")
    progress.add_argument("room_id")
    progress.add_argument("--home", required=True)
    progress.add_argument("--presence", choices=["online", "offline", "unknown"])
    progress.add_argument("--read-to", type=int, dest="last_read_seq")
    preview = commands.add_parser("preview", help="Preview the recipients using the same rule as send")
    preview.add_argument("room_id")
    preview.add_argument("--from", dest="sender_id", required=True)
    preview_reminders = preview.add_mutually_exclusive_group()
    preview_reminders.add_argument("--mention", action="append", default=[], dest="target_ids")
    preview_reminders.add_argument("--notify", action="store_true", default=None)
    preview_reminders.add_argument("--no-notify", action="store_false", dest="notify")
    preview.add_argument("--invite", action="store_true")
    join = commands.add_parser("join", help="Join by global staff number Sxxx or exact Home ID")
    join.add_argument("room_id")
    join.add_argument("--home", required=True, help="Global staff number Sxxx or exact joined Home ID")
    join.add_argument("--label")
    # Seat participation: one CLI per state transition (member state backend).
    # Reads are inherently `members` already; keep the verbs explicit.
    seat = commands.add_parser(
        "seat",
        help="Change seat participation state of a joined Home (participant/observer/left)",
    )
    seat.add_argument("room_id")
    seat.add_argument("--home", required=True,
                      help="Global staff number Sxxx or exact joined Home ID whose seat state changes")
    seat.add_argument(
        "--state",
        required=True,
        choices=["participant", "observer", "left"],
        help=(
            "participant: can receive reminders and speak; "
            "observer: read-only, no reminders, no speech; "
            "left: resigned from seat, history kept, no reminders/speech"
        ),
    )
    send = commands.add_parser("send", help="Post; Human defaults to all participants, Agent defaults to quiet")
    invite = commands.add_parser("invite", help="Invite one Agent with a public message and one reminder")
    for post in (send, invite):
        post.add_argument("room_id")
        post.add_argument("--from", dest="sender_id", required=True,
                          help="Global staff number Sxxx or exact joined Home ID")
        post.add_argument("--body", required=True, help="Literal text, @FILE or '-' for stdin")
        post.add_argument("--message-id", required=True, help="Reuse this ID for idempotent replay")
    invite.add_argument("--to", dest="target_id", required=True, help="Employee to invite to this room")
    send.add_argument("--reply-to", help="Existing message ID in this room")
    send.add_argument("--invite", action="store_true", help="Invite the selected employees in the same message write")
    reminders = send.add_mutually_exclusive_group()
    reminders.add_argument("--mention", action="append", default=[], dest="target_ids",
                           help="Remind this participating employee; repeat for multiple targets")
    reminders.add_argument("--no-notify", action="store_false", dest="notify", default=None,
                           help="Explicitly save quietly")
    reminders.add_argument("--notify", action="store_true", dest="notify",
                           help="Explicitly remind this room's participants")
    read = commands.add_parser("read", help="Read public messages after a sequence number")
    read.add_argument("room_id")
    read.add_argument("--after", type=int, default=0)


def _context_arguments(parser):
    for flag in ("goal", "source-ref", "human-request-ref", "project-id", "index-path"):
        parser.add_argument("--" + flag)


def _task_context(args):
    return {key: getattr(args, key) for key in
            ("goal", "source_ref", "human_request_ref", "project_id", "index_path")
            if getattr(args, key) is not None}


def _room_summary(room: dict) -> dict:
    """`cat show` default AND --json view: output projection only.

    The original GET room still happens; the CLI just trims its echo.
    Room metadata passes through verbatim, lists/dicts become counts, and
    last_seq is `room["messages"][-1]["seq"]` with 0 for an empty room (the
    cursor start; every non-empty message carries seq by backend contract,
    so no field or type guessing and a non-empty bad seq is never folded
    into the empty-room 0). No message bodies are echoed. The full original
    room is only emitted on explicit --full-result; incremental reading via
    cat read --after (cursor, not paged).
    """
    summary: dict = {}
    counts: dict[str, int] = {}
    for key, value in dict(room).items():
        if key == "task_context":
            summary[key] = value
        elif isinstance(value, list):
            counts[key] = len(value)
        elif isinstance(value, dict):
            counts[key] = len(value)
        else:
            summary[key] = value
    messages = room.get("messages")
    if isinstance(messages, list):
        counts["last_seq"] = messages[-1]["seq"] if messages else 0
    summary["counts"] = counts
    summary["full_history"] = "cat read ROOM --after N (incremental cursor); original room via --full-result"
    return summary


def execute_cat(args, client, text_arg):
    command = args.cat_command
    if command == "list":
        query = "?" + urlencode({"home_id": args.home}) if args.home else ""
        return client.request("GET", "/api/rooms" + query)
    if command == "create":
        payload = {"title": args.title}
        for argument, field in (("actor_id", "created_by"), ("owner_id", "owner_id"),
                                ("close_policy", "close_policy")):
            if getattr(args, argument) is not None:
                payload[field] = getattr(args, argument)
        context = _task_context(args)
        if context:
            payload["task_context"] = context
        return client.request("POST", "/api/rooms", payload)
    path = "/api/rooms/" + quote(args.room_id, safe="")
    if command in {"show", "members"}:
        result = client.request("GET", path)
        if command == "members":
            return {"ok": True, "members": result["room"]["members"]}
        if getattr(args, "full_result", False):
            return result
        return {
            "ok": True,
            "room_id": args.room_id,
            "summary": _room_summary(result["room"]),
        }
    if command == "join":
        return client.request("POST", path + "/members", {
            "home_id": args.home, "label": args.label or args.home,
        })
    if command == "seat":
        # Backend contract stays explicit regardless of the CLI keyword chosen;
        # one command per state keeps the error surface single-line honest.
        return client.request(
            "POST",
            path + "/members/" + quote(args.home, safe="") + "/state",
            {"state": args.state},
        )
    if command == "read":
        return client.request("GET", path + "/messages?" + urlencode({"after": args.after}))
    if command == "close":
        payload = {"actor_id": args.actor_id, "action": args.action} if args.actor_id or args.action != "request" else {}
        return client.request("POST", path + "/close", payload)
    if command == "context":
        payload = {"actor_id": args.actor_id, "task_context": _task_context(args)}
        if args.owner_id is not None:
            payload["owner_id"] = args.owner_id
        return client.request("POST", path + "/context", payload)
    if command == "progress":
        payload = {field: getattr(args, field) for field in ("presence", "last_read_seq")
                   if getattr(args, field) is not None}
        return client.request("POST", path + "/members/" + quote(args.home, safe="") + "/progress", payload)
    if command == "preview":
        payload = {
            "sender_id": args.sender_id, "target_ids": args.target_ids, "invite": args.invite,
        }
        if args.notify is not None:
            payload["notify"] = args.notify
        return client.request("POST", path + "/message-preview", payload)
    payload = {
        "message_id": args.message_id,
        "sender_id": args.sender_id,
        "body": text_arg(args.body, "public message", required=True),
    }
    if command == "invite":
        payload.update(target_ids=[args.target_id], invite=True)
    else:
        payload["reply_to"] = args.reply_to
        payload["target_ids"] = args.target_ids
        if args.invite:
            payload["invite"] = True
        if args.notify is not None:
            payload["notify"] = args.notify
    return client.request("POST", path + "/messages", payload)
