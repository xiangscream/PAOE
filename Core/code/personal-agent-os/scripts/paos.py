#!/usr/bin/env python3
"""Command-line boundary: parse -> dispatch -> narrow writer -> response.

Learning path: read ``build_parser`` and ``main`` first, then inspect only the
handler for the command you need.  This is a *controller*, not a second place
to store Project facts. Normal Home work and Library search use files, not an
HTTP dashboard; only explicit CAT/native operations use external transports.
"""
from __future__ import annotations


import argparse
import re
import socket
import json
import locale
import os
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from paos_registry import ProjectRegistry, RegistryProblem
from paos_library import search_library_resources, _validate_tool_catalog_file

from paos_workstation import posix_windows_drive_locator, WorkstationProblem, render_fixed_entry, ensure_fixed_workstation, read_fixed_workstation
from paos_guide import GuideProblem, build_guide_diff
from paos_mail import (  # noqa: E402
    MailProblem,
    dispatch_status,
    list_mail,
    mark_mail_handled,
    read_mail,
    resolve_recipients,
    send_mail,
)
from paos_notice import NoticeProblem  # noqa: E402
from paos_todo import TodoProblem  # noqa: E402
from paos_mail_tracking import handoff_status, sent_task_status, track_sent_mail  # noqa: E402
from paos_mail_claim import (  # noqa: E402
    claim_mail, claim_rooter_mail, result_mail, result_rooter_mail,
)
from paos_agent_activation import (  # noqa: E402
    AgentActivationProblem,
    activate_mail_dispatch,
    send_agent_mail,
)
from paos_home import HomeProblem, agent_project_id, project_agent_home
from paos_attention_service import (  # noqa: E402
    ATTENTION_SERVICE_SCHEMA,
    resolve_home_by_registry,
    AttentionServiceProblem,
    read_source_status as attention_read_source_status,
    register_direct_input as attention_register_direct_input,
    request_cat_activation as attention_request_cat_activation,
    send_cat_source as attention_send_cat_source,
    write_home_todo as attention_write_home_todo,
    update_home_todo_fields as attention_update_home_todo_fields,
    TODO_LIST_FIELDS as attention_todo_list_fields,
    handle_input as attention_handle_input,
    takeover_input as attention_takeover_input,
    mark_input_read as attention_mark_input_read,
    archive_input as attention_archive_input,
    archive_rooter_input as attention_archive_rooter_input,
    read_history_input as attention_read_history_input,
    organize_input as attention_organize_input,
    handle_mail_input as attention_handle_mail_input,
    list_project_mail_inputs as attention_list_project_mail_inputs,
    read_project_mail_input as attention_read_project_mail_input,
    read_home_state as attention_read_home_state,
    request_mail_activation as attention_request_mail_activation,
    resolve_project_home as attention_resolve_project_home,
    resolve_rooter_home as attention_resolve_rooter_home,
    resolve_home_by_registry,
    send_mail_source as attention_send_mail_source,
)
from paos_cat_activation import (  # noqa: E402
    CatActivationProblem,
    activate_cat_exchange,
    send_cat_agent_message,
    verify_cat_exchange_source,
)
from runtime_injection import (  # noqa: E402
    InjectionError,
    InjectionUncertain,
    inject as native_inject,
)
from paos_wakeup import WakeProblem, bind_wakeup  # noqa: E402
from paos_contact import (  # noqa: E402
    load_native_targets,
    save_native_targets,
)
from paos_library import (  # noqa: E402
    LibraryProblem,
    ensure_skill_library,
    ensure_workflow_library,
    load_library_roots,
    record_skill_use,
    refresh_skill_catalog,
    refresh_workflow_catalog,
    register_library_roots,
)
from paos_installation import (
    effective_data_root,  # noqa: E402
    InstallationProblem,
    load_installation_descriptor,
    resolve_installation_path,
    resolve_library_roots_path,
    write_installation_descriptor,
)
ORIENT_SCHEMA = "paos-orient/v1"
INBOX_SCHEMA = "paos-inbox/v1"
from paos_agent_numbers import (
    NumbersProblem,
    agent_id_for_staff_number,
    allocate_number,
    load_numbers,
    resolve_numbers_path,
    staff_number as agent_staff_number,
)
from paos_contact import (  # noqa: E402
    CONTACT_SCHEMA,
    build_team_rows,
    summarize_team_row,
    team_member_statuses,
    parse_team_payload,
    runtime_contact,
)
from paos_cat_cli import add_cat_parser, execute_cat  # noqa: E402
from paos_phase_cli import add_phase_parsers, execute_phase  # noqa: E402
from paos_data_cli import add_data_parsers, execute_data
from paos_team_plan_cli import add_team_parsers, execute_team_actions
from paos_input_cleanup import add_cleanup_parser, execute_cleanup
from paos_todo import TodoProblem
from sqlite3 import Error as SqliteError
PEERS_SCHEMA = "paos-peers/v2"

BODY_HELP = (
    "Markdown body, @FILE, or '-' for stdin. Windows .cmd: use a UTF-8 "
    "@FILE for multiline content; programmatic multiline literals must call "
    "the Python entry directly, not the batch file.")
CAT_BODY_HELP = (
    "CAT message body, @FILE, or '-' for stdin. Windows .cmd: use a UTF-8 "
    "@FILE for multiline content; programmatic multiline literals must call "
    "the Python entry directly, not the batch file.")


from paos_orient import (
    _orient_source_root, _orient_library_roots, _orient_next_action,
    _todo_current_view, _todo_open_tasks, _orient_todo_contract_issues, render_orient,
    read_recovery_inputs, render_recovery_read,
)


class CliError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        error_code: str = "",
        hint: str = "",
        details: dict[str, Any] | None = None,
        operation_id: str | None = None,
        revision: int | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.error_code = error_code
        self.hint = hint
        self.details = dict(details or {})
        self.operation_id = operation_id
        self.revision = revision

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "ok": False,
            "error": str(self),
            "error_code": self.error_code or "cli_error",
            "hint": self.hint,
            "details": self.details,
        }
        if self.status is not None:
            result["status"] = self.status
        if self.operation_id:
            result["operation_id"] = self.operation_id
        if self.revision is not None:
            result["revision"] = self.revision
        return result


class RestClient:
    def __init__(self, base_url: str, timeout: float = 8.0, *, service: str = "PAOS"):
        self.base_url = normalize_base_url(base_url, "base URL")
        self.timeout = timeout
        self.service = service

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        req = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            body: dict[str, Any] = {}
            try:
                candidate = json.loads(raw)
                if isinstance(candidate, dict):
                    body = candidate
            except json.JSONDecodeError:
                pass
            error = body.get("error")
            message = str(error.get("message") if isinstance(error, dict) else error or raw or exc)
            details = body.get("details")
            if not isinstance(details, dict):
                details = {}
            raise CliError(
                message,
                status=exc.code,
                error_code=str(error.get("code") if isinstance(error, dict) else body.get("error_code") or "http_error"),
                hint=str(body.get("hint") or ""),
                details=details,
            ) from exc
        except URLError as exc:
            raise CliError(
                f"{self.service} unreachable: {exc.reason}",
                error_code="unreachable",
                hint=f"Check that {self.service} is running and that the configured base URL is reachable.",
            ) from exc
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CliError(
                f"{self.service} returned non-JSON response",
                error_code="invalid_response",
            ) from exc
        if not isinstance(body, dict):
            raise CliError(
                f"{self.service} returned a non-object JSON response",
                error_code="invalid_response",
            )
        return body


def normalize_base_url(value: str, label: str) -> str:
    text = str(value or "").strip().rstrip("/")
    parsed = urlsplit(text)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise CliError(
            f"{label} must be an http(s) origin such as http://127.0.0.1:8766",
            error_code="invalid_base_url",
        )
    return f"{parsed.scheme}://{parsed.netloc}"


def _decode_stdin_bytes(data: bytes, label: str) -> str:
    """Decode native CLI stdin without inheriting surrogateescape artifacts.

    UTF-8 is the PAOS interchange default. Common Windows native-pipe
    encodings are accepted only as strict fallbacks when the bytes are not
    valid UTF-8.
    """
    if not data:
        return ""

    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass

    candidates: list[str] = ["utf-8"]
    stream_encoding = str(getattr(sys.stdin, "encoding", "") or "").strip()
    if stream_encoding:
        candidates.append(stream_encoding)
    try:
        preferred = locale.getpreferredencoding(False)
    except Exception:
        preferred = ""
    if preferred:
        candidates.append(preferred)
    if os.name == "nt":
        candidates.append("mbcs")

    seen: set[str] = set()
    for encoding in candidates:
        key = encoding.lower().replace("_", "-")
        if key in seen:
            continue
        seen.add(key)
        try:
            return data.decode(encoding, errors="strict")
        except (LookupError, UnicodeDecodeError):
            continue

    raise CliError(
        f"Cannot decode {label} from stdin as UTF-8/native Windows text",
        error_code="text_input_encoding_error",
        hint="Pipe UTF-8 text or use @FILE with a UTF-8 file.",
    )


def _read_stdin_text(label: str) -> str:
    stream = sys.stdin
    binary = getattr(stream, "buffer", None)
    if binary is not None:
        try:
            data = binary.read()
        except OSError as exc:
            raise CliError(
                f"Cannot read {label} from stdin",
                error_code="text_input_error",
            ) from exc
        return _decode_stdin_bytes(data, label)

    # StringIO/test/custom streams have no binary buffer. If a text wrapper
    # already produced surrogateescape code points, recover the original
    # bytes and run them through the same strict decoder.
    text = stream.read()
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in text):
        encoding = str(getattr(stream, "encoding", "") or "utf-8")
        try:
            data = text.encode(encoding, errors="surrogateescape")
        except (LookupError, UnicodeEncodeError) as exc:
            raise CliError(
                f"Cannot recover {label} stdin bytes",
                error_code="text_input_encoding_error",
            ) from exc
        return _decode_stdin_bytes(data, label)
    return text


def text_arg(value: str | None, label: str, *, required: bool = False) -> str:
    """Resolve one text argument from literal text, @FILE, or '-' stdin."""
    if value is None:
        text = ""
    else:
        raw = str(value)
        if raw == "-":
            text = _read_stdin_text(label)
        elif raw.startswith("@@"):
            text = raw[1:]
        elif raw.startswith("@"):
            path = Path(raw[1:]).expanduser()
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise CliError(
                    f"Cannot read {label} from {path}",
                    error_code="text_input_error",
                ) from exc
        else:
            text = raw
    text = text.strip()
    if required and not text:
        raise CliError(
            f"{label} cannot be empty",
            error_code="text_input_error",
        )
    return text


def todo_text_arg(value: str | None, label: str, *, required: bool = False) -> str:
    """Resolve TODO payload without normalizing line endings or outer whitespace."""
    if value is None:
        text = ""
    else:
        raw = str(value)
        if raw == "-":
            text = _read_stdin_text(label)
        elif raw.startswith("@@"):
            text = raw[1:]
        elif raw.startswith("@"):
            path = Path(raw[1:]).expanduser()
            try:
                text = path.read_bytes().decode("utf-8")
            except OSError as exc:
                raise CliError(
                    f"Cannot read {label} from {path}",
                    error_code="text_input_error",
                ) from exc
            except UnicodeError as exc:
                raise CliError(
                    f"Cannot decode {label} from {path} as UTF-8",
                    error_code="text_input_encoding_error",
                ) from exc
        else:
            text = raw
    if required and not text.strip():
        raise CliError(
            f"{label} cannot be empty",
            error_code="text_input_error",
        )
    return text


def get_session_detail(registry, project_id, session_id):
    project = registry.read(project_id)
    session = next((item for item in project["sessions"] if item["id"] == session_id), None)
    if session is None:
        raise CliError("工位成员未登记。", error_code="home_agent_unknown")
    return {"session": session, "project_revision": project.get("revision")}


def find_by_id(
    items: list[dict[str, Any]], object_id: str, label: str
) -> dict[str, Any]:
    for item in items:
        if item.get("id") == object_id:
            return item
    raise CliError(
        f"{label} not found: {object_id}",
        error_code="not_found",
    )


def _read_orient_inputs(
    registry: ProjectRegistry,
    project_id: str,
    agent_id: str,
    *,
    root_override: str | None,
    installation_path: Path,
) -> dict[str, Any]:
    project = registry.read(project_id)
    if not isinstance(project, dict):
        raise CliError("Project response is missing project", error_code="invalid_response")
    detail = get_session_detail(registry, project_id, agent_id)
    session = detail.get("session")
    if not isinstance(session, dict):
        raise CliError("Session Detail is missing session", error_code="invalid_response")

    root_raw = str(root_override or project.get("root_path") or "").strip()
    root = (
        Path(posix_windows_drive_locator(root_raw)).expanduser()
        if root_raw
        else None
    )
    issues: list[dict[str, str]] = []
    workstation_view: dict[str, Any] = {}
    if root is None:
        issues.append(
            {
                "kind": "project_root_missing",
                "detail": "Project 未登记 root_path，且未提供 --root；固定工位不可读。",
            }
        )
    else:
        try:
            workstation_view = read_fixed_workstation(
                root, agent_id, tolerate_todo_errors=True
            )
        except WorkstationProblem as problem:
            issues.append(
                {
                    "kind": "workstation",
                    "code": str(problem.code),
                    "detail": f"固定工位不可读（{problem.code}）：{problem}",
                }
            )
            workstation = root / "Workstations" / agent_id
            workstation_view = {
                "workstation_path": str(workstation),
                "entry_path": str(workstation / "ENTRY.md"),
                "entry_exists": (workstation / "ENTRY.md").is_file(),
                "todo_path": str(workstation / "TODO.md"),
                "todo": {},
                "todo_error": {"code": problem.code, "detail": str(problem)},
                "mailbox": {},
            }

    todo = workstation_view.get("todo") if isinstance(workstation_view.get("todo"), dict) else {}
    todo_error = workstation_view.get("todo_error")
    contract_issues = (
        _orient_todo_contract_issues(todo, project_id, agent_id)
        if workstation_view and not todo_error
        else []
    )
    todo_trusted = bool(workstation_view) and not bool(todo_error) and not contract_issues
    current = _todo_current_view(todo) if todo_trusted else {}
    open_tasks = _todo_open_tasks(todo) if todo_trusted else []
    if todo_error:
        issues.append(
            {
                "kind": "todo_read",
                "code": str(todo_error.get("code") or "todo_unavailable"),
                "detail": str(todo_error.get("detail") or "固定工位 TODO 不可读取。"),
            }
        )
    if contract_issues:
        issues.append(
            {
                "kind": "todo_contract",
                "code": "todo_contract_invalid",
                "detail": "TODO 当前区格式或身份不完整；仍显示固定工位 ENTRY，不从 TODO 历史推断下一步。",
            }
        )

    try:
        installation = load_installation_descriptor(installation_path)
    except InstallationProblem as problem:
        installation = None
        issues.append(
            {
                "kind": "installation_descriptor_invalid",
                "code": problem.code,
                "detail": str(problem),
            }
        )
    installation_roots = _orient_library_roots(installation, issues)
    source_root = _orient_source_root(installation, issues)
    workstation_mailbox = workstation_view.get("mailbox") or {}
    mail_count = int(workstation_mailbox.get("message_count") or 0)
    unhandled_mail_count = 0
    if root is not None and workstation_mailbox.get("ready"):
        try:
            if todo.get("schema") == "paos-todo/v4":
                mail_listing = attention_list_project_mail_inputs(
                    root=root,
                    project=project,
                    agent_id=agent_id,
                )
                mail_count = int(mail_listing.get("count") or 0)
                unhandled_mail_count = int(
                    mail_listing.get("unresolved_count")
                    if mail_listing.get("unresolved_count") is not None
                    else mail_listing.get("pending_count") or 0
                )
            else:
                mail_listing = list_mail(root, agent_id)
                mail_count = int(mail_listing.get("count") or 0)
                unhandled_mail_count = int(mail_listing.get("unhandled_count") or 0)
                for item in mail_listing.get("items") or []:
                    if isinstance(item, dict) and item.get("handling_error"):
                        issues.append(
                            {
                                "kind": "mail_handling_record",
                                "detail": str((item.get("handling_error") or {}).get("detail") or "Mail handled 记录无效。"),
                            }
                        )
        except (MailProblem, AttentionServiceProblem) as problem:
            issues.append(
                {
                    "kind": "durable_mail",
                    "code": str(getattr(problem, "code", "mail_unavailable")),
                    "detail": str(problem),
                }
            )
            unhandled_mail_count = mail_count
    project_root = str(root) if root is not None else ""
    payload = {
        "ok": True,
        "schema": ORIENT_SCHEMA,
        "project_revision": project.get("revision"),
        "identity": {
            "project_id": project_id,
            "project_name": project.get("name"),
            "agent_id": agent_id,
            "identity_id": session.get("identity_id"),
            "agent_label": session.get("agent_label"),
            "status": session.get("status"),
            "registered_home": agent_id in set(project.get("homes") or []),
        },
        "project": {
            "root_path": project_root,
            "source_root": source_root,
            "library_roots": installation_roots,
        },
        "entry": {
            "path": workstation_view.get("entry_path", ""),
            "available": bool(workstation_view.get("entry_exists")),
        },
        "todo": {
            "workstation_path": workstation_view.get("workstation_path", ""),
            "path": workstation_view.get("todo_path", ""),
            "schema": todo.get("schema", ""),
            "trusted": todo_trusted,
            "current": current,
            "open_tasks": open_tasks,
            "counts": todo.get("counts") or {},
            "missing_sections": todo.get("missing_sections") or [],
            "issues": contract_issues,
            "read_error": todo_error,
        },
        "communication": {
            "durable_mail": {
                "state": "ready" if workstation_mailbox.get("ready") else "unavailable",
                "count": mail_count,
                "unhandled_count": unhandled_mail_count,
                "path": workstation_mailbox.get("path", ""),
            },
        },
        "runtime_reachability": "unknown",
        "inconsistencies": issues,
        "next_action": _orient_next_action(
            unhandled_mail_count,
            current,
            open_tasks,
            todo_trusted,
        ),
        "expand": {
            "inbox": f"paos inbox {project_id} {agent_id}",
            "project": f"paos project show {project_id}",
        },
    }
    return payload


def _execute_orient_read(
    args: argparse.Namespace,
    registry: ProjectRegistry,
    installation_path: Path,
) -> Any:
    """Short read-only path: resolve Home and read the five originals only."""
    project = registry.read(args.project_id)
    root_raw = str(args.root or project.get("root_path") or "").strip()
    if not root_raw:
        raise CliError("Project 未登记 root_path，无法读取恢复原文。",
                       error_code="orient_project_root_missing")
    root = Path(posix_windows_drive_locator(root_raw)).expanduser()
    try:
        ref = project_agent_home(project=project, agent_id=args.agent_id,
                                 root_override=str(root), require_existing=True)
    except HomeProblem as problem:
        raise CliError(str(problem), error_code=getattr(problem, "code", "home_unavailable"),
                       details=getattr(problem, "details", {})) from problem
    home = Path(ref["home_path"])
    recovery = read_recovery_inputs(project_root=root, home_path=home)
    failed = [item for item in recovery["documents"]
              if not item["present"] and item["state"] != "optional_missing"]
    if failed:
        detail = [{"key": item.get("key"), "label": item.get("label"),
                   "path": item["path"], "state": item.get("state"), "error": item.get("error")}
                  for item in failed]
        raise CliError(
            "恢复原文缺失或不可读：" + ", ".join(item["path"] for item in failed),
            error_code="orient_read_source_unavailable",
            details={"documents": detail},
        )
    payload = {
        "ok": True,
        "schema": ORIENT_SCHEMA,
        "identity": {
            "project_id": args.project_id,
            "agent_id": args.agent_id,
            "registered_home": args.agent_id in set(project.get("homes") or []),
        },
        "project": {"root_path": str(root)},
        "recovery": recovery,
    }
    label = agent_staff_number(
        args.agent_id,
        explicit_path=str(getattr(args, "agent_numbers_file", None) or ""),
        installation_path=installation_path,
    )
    if label:
        payload["identity"]["staff_number"] = label
        payload["staff_number"] = label
    receiver = None
    if getattr(args, "resume_owner", False):
        receiver = _prepare_resume_receiver(installation_path, ref)
        payload["receiver_preparation"] = receiver
    if args.json_output:
        return payload
    originals = render_recovery_read(payload)
    return f"{receiver['systemMessage']}\n\n{originals}" if receiver else originals


def _prepare_resume_receiver(installation_path, home):
    from codex_receiver_session_start import prepare_current
    from wakeup_native.codex_receiver import ReceiverError

    try:
        message = prepare_current(installation_path=installation_path, expected_home=home)
    except (ReceiverError, InjectionError, InstallationProblem, AttentionServiceProblem,
            HomeProblem, RegistryProblem, WorkstationProblem, OSError, ValueError, KeyError) as problem:
        message = f"receiver_prepare_unavailable: {getattr(problem, 'code', str(problem))}"
    return {
        "ok": message.startswith(("receiver_prepare_started:", "receiver_prepare_reused:")),
        "systemMessage": message,
    }


def execute_orient(
    args: argparse.Namespace,
    registry: ProjectRegistry,
    installation_path: Path,
) -> Any:
    if getattr(args, "resume_owner", False):
        if args.root:
            raise CliError("复工使用本人登记的 Project root。", error_code="orient_resume_root_override")
        return _execute_orient_read(args, registry, installation_path)
    if getattr(args, "read_originals", False):
        return _execute_orient_read(args, registry, installation_path)
    payload = _read_orient_inputs(
        registry,
        args.project_id,
        args.agent_id,
        root_override=args.root,
        installation_path=installation_path,
    )
    label = agent_staff_number(
        args.agent_id,
        explicit_path=str(getattr(args, 'agent_numbers_file', None) or ''),
        installation_path=installation_path,
    )
    if label:
        payload["identity"]["staff_number"] = label
        payload["staff_number"] = label
    return payload if args.json_output else render_orient(payload)


def execute_status(args, registry, installation_path):
    """工位事实 + Contact；不查询已经退出包的 Core HTTP 服务。"""
    view = _read_orient_inputs(registry, args.project_id, args.agent_id,
                               root_override=args.root, installation_path=installation_path)
    root = Path(view["project"]["root_path"])
    result = {"ok": view["ok"], "schema": "paos-status/v2", "work": view,
              "contact": runtime_contact(root, args.agent_id, installation_path=installation_path),
              "backend": "local_files", "http_service_required": False}
    if args.message_id:
        result["delivery"] = dispatch_status(root, args.message_id,
            installation_path=installation_path, project_id=args.project_id,
            registry_lookup=_registry_authoritative_or_none(str(installation_path)))
    return result


def _remind_via_native(
    *,
    root: Path,
    project: dict[str, Any],
    agent_id: str,
    message_id: str,
    sender_id: str,
    subject: str,
    installation_path: Path | None = None,
) -> dict[str, Any]:
    """按本安装的 Home 登记和中央 Contact 向原会话显式提醒一次。"""
    installation_path = installation_path or resolve_installation_path(None)
    route = _rooter_home_root(installation_path)
    if route and agent_id == route[0]:
        # Rooter 身份来自本安装，运行入口走同一 Data Store。
        return _inject_from_contact_store(
            route[1],
            installation_path=installation_path,
            agent_id=agent_id,
            message_id=message_id,
            sender_id=sender_id,
            subject=subject,
        )
    if agent_id == "rooter-001":
        return {
            "agent_id": agent_id,
            "state": "manual_required",
            "reason": (
                "Rooter Home 未在本安装登记（installation descriptor 无 "
                "rooter_home）；不伪造 cross-Installation 目标。"
            ),
        }
    invoked_members = {
        str(s.get("id") or "")
        for s in (project.get("sessions") or [])
        if isinstance(s, dict)
    }
    is_cross_project = agent_id not in invoked_members
    contact_home_root = None
    if is_cross_project:
        # 先核对跨项目工位属于所选安装，再使用中央 Contact。
        # registry Home 提供真实 project_root（Windows C:/ 形态），按现有
        # posix_windows_drive_locator 转换为实际可读取的真实磁盘定位。
        try:
            home_ref = resolve_home_by_registry(agent_id, installation_file=str(installation_path))
            project_root_text = str(home_ref.get("project_root") or "").strip()
            contact_home_root = (
                Path(posix_windows_drive_locator(project_root_text))
                if project_root_text else None
            )
        except AttentionServiceProblem as problem:
            return {
                "agent_id": agent_id,
                "state": "manual_required",
                "reason": f"跨 Project Home 未能按 registry 解析：{problem}",
            }
        if contact_home_root is None or not contact_home_root.is_dir():
            return {
                "agent_id": agent_id,
                "state": "manual_required",
                "reason": "跨 Project Home 的 Contact 文件目录真实不存在。",
            }
    else:
        # 本 Project：execute_agent 已经拿到真实 root；无需读全局 registry。
        contact_home_root = Path(root)
    return _inject_from_contact_store(
        contact_home_root,
        installation_path=installation_path,
        agent_id=agent_id,
        message_id=message_id,
        sender_id=sender_id,
        subject=subject,
    )


def _native_target_for_home(
    targets: dict[str, Any], agent_id: str,
    installation_file: str | None = None,
) -> dict[str, Any] | None:
    """Exact current key first, then the one historical Home alias key."""
    exact = targets.get(agent_id)
    if isinstance(exact, dict):
        return exact
    try:
        current = str(resolve_home_by_registry(
            agent_id, installation_file=installation_file)["home_id"])
    except (AttentionServiceProblem, HomeProblem, CliError):
        return None
    for key, target in targets.items():
        if not isinstance(target, dict) or key == agent_id:
            continue
        try:
            if str(resolve_home_by_registry(
                    key, installation_file=installation_file)["home_id"]) == current:
                return target
        except (AttentionServiceProblem, HomeProblem, CliError):
            continue
    return None


def _inject_from_contact_store(
    contact_home_root: Path,
    *,
    agent_id: str,
    message_id: str,
    sender_id: str,
    subject: str,
    installation_path: Path | None = None,
) -> dict[str, Any]:
    """One-shot native reminder through the selected installation's Contact store.

    Shared by Project Agents and the installation-registered Rooter Home so the
    same official target drives record, status and reminder. Missing target,
    STOP, uncertain/network/rejected outcomes stay honest; nothing is resent.
    """
    target_map = load_native_targets(contact_home_root, installation_path=installation_path) or {}
    target = _native_target_for_home(target_map, agent_id, str(installation_path) if installation_path else None)
    if not isinstance(target, dict):
        return {
            "agent_id": agent_id,
            "state": "manual_required",
            "reason": f"本安装尚未登记 {agent_id} 的原生联系入口，请从本人工位配置 wake bind",
        }
    stop_file = str((target or {}).get("stop_file") or "")
    if stop_file and Path(posix_windows_drive_locator(stop_file)).exists():
        return {
            "agent_id": agent_id,
            "state": "native_stopped",
            "error_code": "native_stopped",
            "accepted": False,
            "retry": False,
            "repair_owner": agent_id,
            "next_action": "尊重原STOP；只有原授权主体可解除，不自动重投。",
            "reason": "STOP file present; owner explicitly paused",
        }
    message = f"{sender_id} 发来新消息：{subject}\n请读原信，接着处理。\n（原信：{message_id}）"
    try:
        receipt = native_inject(target=target, message=message)
    except InjectionUncertain as problem:
        return {
            "agent_id": agent_id,
            "state": "delivery_uncertain",
            "accepted": None,
            "retry": False,
            "reason": str(problem),
            "error_type": type(problem).__name__,
            **problem.details(),
            "repair_owner": agent_id,
        }
    except (OSError, URLError, socket.timeout) as problem:
        # 保留已落 mail；网络未确认与系统真实错误不冒称 native_rejected。
        return {
            "agent_id": agent_id,
            "state": "network_unconfirmed",
            "accepted": None,
            "retry": False,
            "reason": str(problem),
            "error_type": type(problem).__name__,
        }
    except (InjectionError, ValueError) as problem:
        return {
            "agent_id": agent_id,
            "state": "native_rejected",
            "accepted": False,
            "reason": str(problem),
            "error_type": type(problem).__name__,
            **(problem.details() if isinstance(problem, InjectionError) else {}),
            "repair_owner": (agent_id if problem.repair_owner == "target_owner" else problem.repair_owner) if isinstance(problem, InjectionError) else "sender",
        }
    if not isinstance(receipt, dict) or receipt.get("accepted") is not True:
        # A call returned without its success contract; delivery is not known.
        return {
            "agent_id": agent_id,
            "state": "delivery_uncertain",
            "accepted": None,
            "retry": False,
            "reason": "native_inject returned no confirmed acceptance; do not resend",
            "error_type": "receipt_shape_unexpected",
        }
    normalized = {
        "agent_id": agent_id,
        "state": "native_accepted",
        "accepted": True,
        "runtime": receipt.get("runtime"),
        "session_id": receipt.get("session_id"),
        "http_status": receipt.get("http_status"),
        "native_state": receipt.get("native_state"),
    }
    for key in ("request_id", "reason", "error_type", "native_status_before_submit"):
        if receipt.get(key):
            normalized[key] = receipt.get(key)
    return normalized


def _mail_item_pending(item: dict[str, Any]) -> bool:
    if str(item.get("input_state") or "") in {"pending", "handled"}:
        return str(item.get("input_state")) == "pending"
    return not bool(item.get("handled"))


def _rank_inbox_mail_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pending input first, both groups newest-first by created_at."""

    def newest_first(item: dict[str, Any]) -> str:
        return str(item.get("created_at") or "")

    pending = sorted(
        (item for item in items if _mail_item_pending(item)),
        key=newest_first,
        reverse=True,
    )
    handled = sorted(
        (item for item in items if not _mail_item_pending(item)),
        key=newest_first,
        reverse=True,
    )
    return pending + handled


def execute_inbox(
    args: argparse.Namespace,
    registry: ProjectRegistry,
) -> Any:
    project = registry.read(args.project_id)
    if not isinstance(project, dict):
        raise CliError("Project response is missing project", error_code="invalid_response")
    get_session_detail(registry, args.project_id, args.agent_id)
    root_raw = str(args.root or project.get("root_path") or "").strip()
    durable_mail: dict[str, Any] = {
        "state": "unavailable",
        "path": "",
        "count": 0,
        "items": [],
    }
    if root_raw:
        root = Path(posix_windows_drive_locator(root_raw)).expanduser()
        try:
            workstation = read_fixed_workstation(
                root,
                args.agent_id,
                tolerate_todo_errors=True,
            )
            todo_schema = str((workstation.get("todo") or {}).get("schema") or "")
            if todo_schema == "paos-todo/v4":
                listed = attention_list_project_mail_inputs(
                    root=root,
                    project=project,
                    agent_id=args.agent_id,
                )
                pending_count = int(
                    listed.get("unresolved_count")
                    if listed.get("unresolved_count") is not None
                    else listed.get("pending_count") or 0
                )
                path_value = str(root / "Workstations" / args.agent_id / "mailbox")
            else:
                listed = list_mail(root, args.agent_id)
                pending_count = int(listed.get("unhandled_count") or 0)
                path_value = str(listed.get("mailbox_path") or "")
            ranked = _rank_inbox_mail_items(listed.get("items", []) or [])
            shown = ranked[:6]
            pending_shown = sum(1 for item in shown if _mail_item_pending(item))
            durable_mail = {
                "state": "ready",
                "path": path_value,
                "count": listed.get("count", 0),
                "unhandled_count": pending_count,
                "items": shown,
                "items_shown": len(shown),
                "unhandled_hidden": max(0, pending_count - pending_shown),
                "omitted": max(0, int(listed.get("count", 0)) - 6),
                "ordering": "pending first, then by created_at descending",
                "expand_with": f"paos mail list {args.project_id} {args.agent_id}",
            }
        except (MailProblem, AttentionServiceProblem, WorkstationProblem) as problem:
            durable_mail.update(
                {
                    "state": "missing" if problem.code == "mailbox_missing" else "unreadable",
                    "error_code": problem.code,
                    "detail": str(problem),
                    "path": (problem.details or {}).get("path", ""),
                }
            )
    else:
        durable_mail["detail"] = "Project 未登记 root_path，且未提供 --root。"

    payload = {
        "ok": durable_mail["state"] == "ready",
        "schema": INBOX_SCHEMA,
        "project_id": args.project_id,
        "agent_id": args.agent_id,
        "project_revision": project.get("revision"),
        "durable_mail": durable_mail,
        "runtime_reachability": {"state": "unknown", "checked": False},
        "message_consumption": {"state": "not_observed", "source": "inbox read does not inspect CAT Exchanges or native Runtime turns"},
        "business_result_delivery": {"state": "not_inferred"},
        "business_acceptance": {"state": "not_inferred"},
        "expand": {
            "mail_list": f"paos mail list {args.project_id} {args.agent_id}",
            "project": f"paos project show {args.project_id}",
        },
    }
    if args.json_output:
        return payload
    lines = [
        f"PAOS inbox — {args.agent_id} @ {args.project_id}",
        f"Durable Workstation Mail: {durable_mail.get('state')} ({durable_mail.get('count', 0)})；未处理 {durable_mail.get('unhandled_count', 0)}；其余用 {durable_mail.get('expand_with', 'paos mail list …')} 查看",
        "Runtime reachability: unknown (not probed)",
        "Message consumption/reply: not observed by this read",
        "Business result delivery/acceptance: not inferred from Mail presence",
    ]
    for item in durable_mail.get("items") or []:
        marker = " [未处理]" if _mail_item_pending(item) else ""
        lines.append(f"  Mail{marker} · {item.get('message_id')}: {item.get('subject') or ''}")
    if durable_mail.get("omitted"):
        lines.append(
            f"  …其余 {durable_mail['omitted']} 封用 {durable_mail.get('expand_with', 'paos mail list …')} 查看"
            f"（未处理隐藏 {durable_mail.get('unhandled_hidden', 0)} 封）"
        )
    return "\n".join(lines)


def _roster_root(
    args: argparse.Namespace,
    registry: ProjectRegistry,
) -> tuple[Path, dict[str, Any]]:
    project = registry.read(args.project_id)
    root_raw = str(getattr(args, "root", None) or project.get("root_path") or "").strip()
    if not root_raw:
        raise CliError(
            "未提供 --root，且 Project 没有 root_path；无法定位 Workstations。",
            error_code="contact_project_root_missing",
        )
    root = Path(posix_windows_drive_locator(root_raw)).expanduser()
    return root, project


def _apply_fresh_probe(root: Path, entry: dict[str, Any]) -> None:
    """Workless: no automatic probing；状态保持 never probed。"""
    runtime = entry["runtime_contact"]
    runtime.update({"state_basis": "probe_never_run", "checked_at": None})


def _installation_support_contacts(registry: ProjectRegistry,
                                   numbers_map: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Expose the registered Rooter locator, not a fake Project member or live status."""
    descriptor = load_installation_descriptor(registry.installation_path)
    raw = str(descriptor.get("rooter_home") or "").strip()
    if not raw:
        return []
    home = Path(posix_windows_drive_locator(raw)).expanduser()
    entry = home / "ENTRY.md"
    rooter_label = (numbers_map or {}).get("rooter-001") or "rooter-001"
    return [{
        "agent_id": "rooter-001",
        "home_kind": "rooter",
        "scope": "installation",
        "purpose": "安装、Runtime 入口与恢复维护",
        "home_path": str(home),
        "entry_path": str(entry),
        "entry_exists": entry.is_file(),
        "runtime_state": "not_probed",
        "send_hint": f"agent send <本人项目ID> --to {rooter_label} --remind",
        "contact_hint": f"wake status rooter {rooter_label}",
    }]


def execute_team(
    args: argparse.Namespace,
    registry: ProjectRegistry,
) -> Any:
    root, project = _roster_root(args, registry)
    numbers_map = _staff_numbers_map(args)
    agents = build_team_rows(project, root, installation_path=registry.installation_path, numbers_map=numbers_map)["agents"]
    if bool(getattr(args, "summary", False)):
        statuses = team_member_statuses(
            str(root / "TEAM.md"), [str(entry.get("agent_id") or "") for entry in agents],
            numbers_map=numbers_map)
        agents = [summarize_team_row(entry, statuses) for entry in agents]
    for entry in agents:
        if bool(getattr(args, "probe", False)):
            _apply_fresh_probe(root, entry)
    installation = load_installation_descriptor(registry.installation_path)
    payload = {
        "ok": True,
        "schema": CONTACT_SCHEMA,
        "project_id": args.project_id,
        "agent_id": args.agent_id,
        "roster_filter": "fixed_workstation",
        "roster_scope": "project_registry",
        "agents": agents,
        "coordinator_home_id": project.get("coordinator_home_id"),
        "team_source": {"path": str(root / "TEAM.md"), "exists": (root / "TEAM.md").is_file()},
        "installation_support": _installation_support_contacts(registry, numbers_map),
        "meta": {
            "backend": "local_files",
            "installation": installation,
            "note": (
                "TEAM=长期固定工位名册，与 Session 状态分离；本读面不探测原生 Runtime，"
                "--probe 是兼容性 no-op；Contact 只显示已登记的事实，不据此声称在线或实际接手。"
                "人工打开会话与实际提醒分开；本命令不启动 Harness。"
            ),
        },
    }
    if bool(getattr(args, "summary", False)):
        payload["summary"] = True
    if args.json_output:
        return payload
    return render_contact(
        payload, include_self=True,
        subject_label=numbers_map.get(str(args.agent_id)) or "员工号未登记")


def execute_peers(args: argparse.Namespace, registry: ProjectRegistry) -> Any:
    root, project = _roster_root(args, registry)
    numbers_map = _staff_numbers_map(args)
    # peers 与 team 共用 TEAM 长期固定工位名册（fixed_workstation 接线），
    # 排除请求本人；既有 JSON 读面键保留。Session 状态退为历史事实
    # （completed/abandoned 但正式 Home 在 → 仍列出）；名册在场不冒称在线
    # （无 --probe 不探测/启动模型、online 状态保持未知）。读面不写数据。
    roster = build_team_rows(project, root, installation_path=registry.installation_path, numbers_map=numbers_map)["agents"]
    if bool(getattr(args, "summary", False)):
        statuses = team_member_statuses(
            str(root / "TEAM.md"), [str(entry.get("agent_id") or "") for entry in roster],
            numbers_map=numbers_map)
        roster = [summarize_team_row(entry, statuses) for entry in roster]
    peers: list[dict[str, Any]] = [
        entry
        for entry in roster
        if str(entry.get("agent_id") or "") != str(args.agent_id)
    ]
    if bool(getattr(args, "probe", False)):
        for entry in peers:
            _apply_fresh_probe(root, entry)
    payload = {
        "ok": True,
        "schema": PEERS_SCHEMA,
        "project_id": args.project_id,
        "agent_id": args.agent_id,
        "roster_filter": "fixed_workstation",
        "roster_scope": "project_registry",
        "peers": peers,
        "coordinator_home_id": project.get("coordinator_home_id"),
        "team_source": {"path": str(root / "TEAM.md"), "exists": (root / "TEAM.md").is_file()},
        "installation_support": _installation_support_contacts(registry, numbers_map),
    }
    if bool(getattr(args, "summary", False)):
        payload["summary"] = True
    if args.json_output:
        return payload
    return render_contact(
        payload, include_self=False,
        subject_label=numbers_map.get(str(args.agent_id)) or "员工号未登记")


def _staff_numbers_map(args: argparse.Namespace) -> dict[str, str]:
    """Read-only staff-number lookup for contact rows; unknown agents stay blank."""
    try:
        resolved_installation_path = resolve_installation_path(
            getattr(args, "installation_file", None)
        )
        numbers_path = resolve_numbers_path(
            getattr(args, "agent_numbers_file", None),
            resolved_installation_path,
        )
        from paos_agent_numbers import load_numbers

        return load_numbers(numbers_path)
    except Exception:
        return {}


def render_contact(payload: dict[str, Any], *, include_self: bool,
                   subject_label: str = "") -> str:
    label = "team" if (payload.get("schema") or "") == CONTACT_SCHEMA else "peers"
    agents = payload.get("agents") if include_self else (payload.get("peers") or [])
    body = dict(payload)
    body["agents"] = agents
    body["agent_id"] = payload.get("agent_id")
    filter_note = payload.get("roster_filter") or "unknown"
    lines = [
        f"PAOS {label} — {subject_label or payload.get('agent_id')} @ {payload.get('project_id')}",
        f"Roster ({filter_note}): {len(agents)}",
    ]
    parse_team_payload(body, lines)
    source = payload.get("team_source") or {}
    if source.get("path"):
        lines.append(f"TEAM roles source: {source['path']} (exists={source.get('exists', False)})")
    for support in payload.get("installation_support") or []:
        lines.append(
            f"Installation support: {support['agent_id']} ({support['purpose']}); "
            f"ENTRY={support['entry_path']} (exists={support['entry_exists']}); "
            f"contact={support['contact_hint']}; runtime={support['runtime_state']}"
        )
    meta = payload.get("meta") or {}
    installation = meta.get("installation") or {}
    if isinstance(installation, dict) and installation:
        lines.append(f"Installation locator: {installation.get('path') or 'not configured'}")
        if installation.get("source_root"):
            lines.append(f"Source root: {installation.get('source_root')}")
    note = str(meta.get("note") or "")
    if note:
        lines.append(f"Note: {note}")
    return "\n".join(lines)


def _validate_new_staff_homes(registry: ProjectRegistry, project_id: str, homes: list[str],
                              installation_path: Path) -> None:
    staff = {home for home in homes if re.fullmatch(r"S\d{3,}", home)}
    if not staff:
        return
    numbers = load_numbers(resolve_numbers_path(None, installation_path))
    directory = registry._path(project_id).parent
    existing = set()
    for path in directory.glob("*.json"):
        registered = staff.intersection(registry.read_record(path.stem)["homes"])
        if registered and path.stem == project_id:
            existing.update(registered)
        elif registered:
            raise CliError(f"员工号已在项目 {path.stem}：{', '.join(sorted(registered))}",
                           error_code="staff_home_already_registered")
    reserved = (staff - existing).intersection(label for home, label in numbers.items() if home != label)
    if reserved:
        raise CliError(f"员工号已分配给原工位：{', '.join(sorted(reserved))}",
                       error_code="staff_home_requires_migration")


def _allocate_staff_number(args: argparse.Namespace, installation_path: Path) -> str:
    try:
        session_id = str(args.session_id or "").strip()
        numbers_path = resolve_numbers_path(
            getattr(args, "agent_numbers_file", None),
            installation_path,
        )
        if re.fullmatch(r"S\d{3,}", session_id):
            # New physical workstations are born with their global S number;
            # migrated staff already have that S as a value under the old key.
            # Do not add a duplicate S->S entry for them.
            if session_id in load_numbers(numbers_path).values():
                return session_id
            return allocate_number(numbers_path, session_id, explicit_label=session_id)
        return allocate_number(numbers_path, session_id)
    except NumbersProblem as exc:
        if getattr(exc, "code", None) == "agent_numbers_not_configured":
            return ""
        raise


def execute_workstation(
    args: argparse.Namespace,
    registry: ProjectRegistry,
    installation_path: Path,
) -> dict[str, Any]:
    """Create/read files for an already registered stable Home."""
    project = registry.read(args.project_id)
    root_raw = args.root or str(project.get("root_path") or "").strip()
    if not root_raw:
        raise CliError(
            "未提供 --root，且 Project 没有 root_path；无法选择工作区。",
            error_code="workstation_root_missing",
            hint="请显式传入 --root，或在 Project 中登记 root_path。",
        )
    root_raw = posix_windows_drive_locator(root_raw)
    root = Path(root_raw).expanduser()

    if args.workstation_command == "init":
        if getattr(args, "protocols_root", None):
            raise CliError(
                "--protocols-root 已退役；请指定实际 System/Guide 目录的 --guide-root。",
                error_code="workstation_protocols_root_retired",
            )
        detail = get_session_detail(registry, args.project_id, args.session_id)
        session = detail.get("session") or {}
        workflow_library = str(getattr(args, "workflow_library", None) or "")
        skill_library = str(getattr(args, "skill_library", None) or "")
        try:
            installation = load_installation_descriptor(installation_path)
            roots_path = resolve_library_roots_path(installation=installation)
            roots = load_library_roots(roots_path)
            if not workflow_library:
                workflow_library = str(roots.get("workflow_root") or "")
            if not skill_library:
                skill_library = str(roots.get("skill_root") or "")
            entry_args = dict(
                workflow_library=workflow_library,
                guide_root=str(getattr(args, "guide_root", None) or ""),
                entry_template=str(getattr(args, "entry_template", None) or ""),
                skill_library=skill_library,
                tool_index_ref=str(roots.get("tool_catalog") or ""),
                installation_file=str(installation_path),
                library_roots_config=str(roots_path),
                source_root=str(installation.get("source_root") or ""),
            )
            # Reject broken/missing templates before even allocating a number.
            render_fixed_entry(project=project, session=session,
                               workstation_path=root / "Workstations" / args.session_id,
                               **entry_args)
            staff = _allocate_staff_number(args, installation_path)
            result = ensure_fixed_workstation(
                root=root, project=project, session=session,
                objective=str(getattr(args, "objective", None) or ""),
                staff_number=staff, **entry_args,
            )
        except (WorkstationProblem, LibraryProblem, InstallationProblem) as problem:
            raise CliError(
                str(problem),
                error_code=getattr(problem, "code", "workstation_error"),
                details=problem.details,
            ) from None
        return {
            "ok": True,
            "schema": "paos-workstation-home/v1",
            **result,
        }

    if args.workstation_command == "show":
        try:
            result = read_fixed_workstation(root, args.session_id)
        except WorkstationProblem as problem:
            raise CliError(
                str(problem),
                error_code=problem.code,
                details=problem.details,
            ) from None
        return {
            "ok": True,
            "schema": "paos-workstation-home-view/v1",
            "project_id": args.project_id,
            "agent_id": args.session_id,
            **result,
        }

    if args.workstation_command == "guide-diff":
        try:
            result = build_guide_diff(
                Path(posix_windows_drive_locator(str(args.candidate))).expanduser(),
                canonical_src=Path(
                    posix_windows_drive_locator(str(args.canonical))
                ).expanduser(),
            )
        except GuideProblem as problem:
            raise CliError(
                str(problem), error_code=problem.code, details=problem.details
            ) from None
        return {"ok": True, **result}

def _home_uses_todo(root: Path, agent_id: str) -> bool:
    """Verify the registered v4 TODO marker; unknown Homes fail closed."""

    def _frontmatter_schema(raw: bytes) -> str:
        for line in raw.splitlines():
            text = line.decode("utf-8", "replace").strip()
            if text.startswith("schema:"):
                return text.split(":", 1)[1].strip().strip('"')
        return ""

    legacy_entry = root / ".paos" / "agents" / agent_id / "ENTRY.md"
    if legacy_entry.exists():
        raise WorkstationProblem(
            "workstation_dual_entry_detected",
            "同时发现 V1.1 固定工位与旧 .paos Agent ENTRY；拒绝静默选择入口。",
            {
                "legacy_entry_path": str(legacy_entry),
                "fixed_entry_path": str(root / "Workstations" / agent_id / "ENTRY.md"),
                "recovery": "运行 workstation init 完成旧生成入口退役；若旧文件含人为内容，先人工确认并移走。",
            },
        )
    todo_file = root / "Workstations" / agent_id / "TODO.md"
    if todo_file.is_symlink() or (not todo_file.is_file() and todo_file.exists()):
        raise WorkstationProblem(
            "workstation_todo_unreadable",
            f"固定工位 TODO.md 定位异常（符号链接/目录冲突），拒绝解读合同：{todo_file}",
            {"todo_path": str(todo_file)},
        )
    if not todo_file.is_file():
        raise WorkstationProblem("workstation_todo_missing", f"TODO 不存在：{todo_file}")
    try:
        raw = todo_file.read_bytes()[:4096]
    except OSError as exc:
        # 真实读取失败必须可定位拒绝，不得用 False 掩盖成 legacy。
        raise WorkstationProblem(
            "workstation_todo_unreadable",
            f"无法读取固定工位 TODO.md：{todo_file}",
            {"todo_path": str(todo_file), "reason": str(exc)},
        ) from exc
    schema = _frontmatter_schema(raw)
    if schema != "paos-todo/v4":
        raise WorkstationProblem("workstation_todo_schema_invalid", f"TODO 需要 paos-todo/v4，实际为 {schema or '缺失'}")
    return True


def _resolve_agent_identity(
    identity: str, *, installation_path: Path | None = None,
) -> dict[str, Any]:
    """Read-only identity entry for the independent CAT adapter.

    The CAT backend may ask with its historical `home_id` or the canonical
    S number. This returns the one registered Home and Project; it never
    creates a seat, a mapping, or a Runtime.
    """
    try:
        ref = resolve_home_by_registry(
            identity, installation_file=str(installation_path or "") or None)
    except AttentionServiceProblem as problem:
        raise CliError(str(problem), error_code=problem.code,
                       details=problem.details) from problem
    except HomeProblem as problem:
        raise CliError(str(problem), error_code=problem.code,
                       details=problem.details) from problem
    try:
        numbers = load_numbers(resolve_numbers_path(
            None, installation_path or Path(__file__).parent))
    except NumbersProblem as problem:
        raise CliError(f"员工号登记不可用：{problem}",
                       error_code=problem.code,
                       details=problem.details) from problem
    home_id = str(ref["home_id"])
    if home_id.upper().startswith("S") and home_id[1:].isdigit():
        staff_number = home_id
        aliases = sorted(
            key for key, value in numbers.items()
            if value.upper() == home_id.upper() and key != home_id)
    else:
        staff_number = str(numbers.get(home_id) or "")
        aliases = [home_id] if home_id in numbers else []
    if len(aliases) > 1:
        raise CliError(
            f"员工 {home_id} 对应多个历史 Home，无法给出唯一遗留别名：{aliases}",
            error_code="attention_recipient_home_ambiguous",
            details={"home_id": home_id, "matches": aliases},
        )
    return {
        "ok": True,
        "schema": "paos-agent-identity/v1",
        "input": identity,
        "home_id": home_id,
        "staff_number": staff_number,
        "legacy_home_id": aliases[0] if aliases else "",
        "project_id": ref["project_id"],
        "home_kind": ref["home_kind"],
        "home_path": ref["home_path"],
    }


def _resolve_staff_number_recipients(args: argparse.Namespace) -> list[str]:
    """Resolve S numbers through the registered local staff map.

    This is the one CLI identity boundary for normal Home and recipient
    parameters. Home ids stay machine locators; an explicit Sxxx token resolves
    through the current registry (or the still-registered old Home before
    migration). Unknown/ambiguous mappings raise instead of falling back.
    """
    installation_path = getattr(args, "installation_file", None) or resolve_installation_path()
    resolved: list[str] = []

    def _swap(token: str) -> str:
        token = str(token).strip()
        if token.upper().startswith("S") and token[1:].isdigit():
            # resolve_home_by_registry returns the real current Home: post-
            # migration Sxxx, or the still-registered old Home pre-migration.
            try:
                ref = resolve_home_by_registry(
                    token, installation_file=str(installation_path))
                return str(ref["home_id"])
            except AttentionServiceProblem as problem:
                # Preserve the CLI's existing precise number errors for an
                # unknown/history-only S. Broken number config is not caught.
                if problem.code != "attention_recipient_home_not_registered":
                    raise
                return agent_id_for_staff_number(
                    token,
                    explicit_path=getattr(args, "agent_numbers_file", None),
                    installation_path=installation_path)
        return token

    to_value = getattr(args, "to", None)
    if isinstance(to_value, list):
        args.to = [_swap(raw) for raw in list(to_value)]
        resolved = list(args.to)
    elif isinstance(to_value, (str, bytes)) and str(to_value or "").strip():
        args.to = _swap(str(to_value))
    agents = getattr(args, "agents", None)
    if isinstance(agents, list):
        args.agents = [_swap(raw) for raw in list(agents)]
    resolved_fields: dict[str, tuple[str, str]] = {}
    for field in ("agent_id", "session_id", "sender_id", "from_agent",
                  "home_id", "coordinator"):
        value = getattr(args, field, None)
        if isinstance(value, (str, bytes)) and str(value or "").strip():
            original = str(value).strip()
            mapped = _swap(original)
            setattr(args, field, mapped)
            if mapped != original and original.upper().startswith("S") and original[1:].isdigit():
                resolved_fields[field] = (original.upper(), mapped)
    args._staff_number_resolved = resolved_fields
    home_values = getattr(args, "home", None)
    if isinstance(home_values, list):
        args.home = [_swap(raw) for raw in list(home_values)]
    elif isinstance(home_values, (str, bytes)) and str(home_values or "").strip():
        original = str(home_values).strip()
        mapped = _swap(original)
        args.home = mapped
        if mapped != original and original.upper().startswith("S") and original[1:].isdigit():
            resolved_fields["home"] = (original.upper(), mapped)
    return resolved


def _validate_resolved_identity_subject(args: argparse.Namespace,
                                         registry: ProjectRegistry,
                                         installation_path: Path) -> None:
    """Reject a direct/resolved Home that is not currently registered.

    Sxxx maps through the installation SSOT; direct Home IDs are checked too, so
    a historical Home cannot bypass a normal read/wake command. Creation and
    explicit registration commands are excluded.
    """
    resolved_fields = getattr(args, "_staff_number_resolved", {}) or {}
    if args.command == "cat":
        home_pattern = re.compile(r"^(?:\d+-s\d+|rooter-001)$")
        for field in ("home", "sender_id"):
            value = str(getattr(args, field, "") or "").strip()
            entry = resolved_fields.get(field)
            if not value or not (entry or home_pattern.match(value)):
                continue
            label = entry[0] if entry else value
            try:
                resolve_home_by_registry(value, installation_file=str(installation_path))
            except (AttentionServiceProblem, HomeProblem, CliError) as exc:
                raise CliError(
                    f"员工号/Home {label} 未登记或已退役。",
                    error_code=("staff_number_history_unregistered" if entry else "home_agent_unknown"),
                    details={"staff_number": label, "agent_id": value},
                ) from exc
        return
    if args.command not in {"status", "orient", "inbox", "peers", "team", "wake"}:
        return
    home = str(getattr(args, "agent_id", "") or "").strip()
    if not home:
        return
    entry = resolved_fields.get("agent_id")
    label = entry[0] if entry else home
    error_code = "staff_number_history_unregistered" if entry else "home_agent_unknown"
    project_id = str(getattr(args, "project_id", "") or "").strip()
    if project_id == "rooter":
        route = _rooter_home_root(installation_path)
        if route and home == route[0]:
            return
        raise CliError(
            f"员工号/Home {label} 映射到 {home}，但不是本安装 Rooter Home。",
            error_code=error_code,
            details={"staff_number": label, "agent_id": home, "project_id": project_id},
        )
    try:
        project = registry.read(project_id)
    except (CliError, RegistryProblem):
        return
    if home not in set(project.get("homes") or []):
        raise CliError(
            f"员工号/Home {label} 映射到未登记 Home {home}；不能当普通未绑定目标。",
            error_code=error_code,
            details={"staff_number": label, "agent_id": home, "project_id": project_id},
        )


def _cross_project_target_lookup(
    registry: ProjectRegistry,
    root: Path,
    target_agent_id: str,
) -> Callable[[str], dict[str, Any]] | None:
    """Cross-project targeted CAT lookup: routes only when the recipient is
    a PRECISE registered member of its own project (deterministic `<pid>-sxxx`
    convention) whose registered Home actually exists — never a guessed
    home/participant.  paos-todo/v4 enforcement is done by the service
    (`_assert_home_current` → `attention_home_not_v4`), so callers verify
    membership + house existence only.  Returns a lookup callable or None
    (None => keep the invoked-project path unchanged)."""
    try:
        home_ref = resolve_home_by_registry(
            target_agent_id, installation_file=str(registry.installation_path))
        project_id = str(home_ref.get("project_id") or "")
        project = registry.read(project_id)
    except (CliError, AgentActivationProblem, AttentionServiceProblem, HomeProblem):
        # Non-project ids (rooter-001 etc.) never enter the cross-project
        # branch: keep the invoked-project path unchanged instead of leaking.
        return None
    if not isinstance(project, dict):
        return None
    sessions = [i for i in (project.get("sessions") or []) if isinstance(i, dict)]
    if not any(str(i.get("id") or "") == target_agent_id for i in sessions):
        return None
    # NOTE: v4 enforcement happens in the service (`_assert_home_current` raises
    # `attention_home_not_v4`), so non-v4 targets get the precise error code
    # instead of a misleading home_agent_unknown.
    return lambda _pid: project

def _recipient_contract(*, root: Path, recipients: list[str]) -> str:
    """Only the current Home contract is routable; unknown/missing Homes fail.

    No legacy mail/activation fallback is created for newly registered Homes.
    """
    if not recipients:
        return "empty"
    for agent_id in recipients:
        _home_uses_todo(root, agent_id)
    return "v4"


def _registered_rooter_home(
    installation_path: Path,
    *,
    home_id: str = "rooter-001",
    require_todo_current: bool = True,
) -> dict[str, Any]:
    try:
        descriptor = load_installation_descriptor(installation_path)
    except InstallationProblem as problem:
        raise CliError(
            str(problem),
            error_code=problem.code,
            details=problem.details,
        ) from None
    rooter_home = str(descriptor.get("rooter_home") or "").strip()
    if not descriptor.get("configured") or not rooter_home:
        raise CliError(
            "installation descriptor 未登记 Rooter Home。",
            error_code="rooter_home_not_registered",
            hint="先用 paos install configure --rooter-home <absolute-path> 登记。",
        )
    try:
        return attention_resolve_rooter_home(
            home_path=rooter_home,
            home_id=home_id,
            require_todo_current=require_todo_current,
        )
    except AttentionServiceProblem as problem:
        raise CliError(
            str(problem),
            error_code=problem.code,
            details=problem.details,
        ) from None


def _rooter_home_root(installation_path: Path) -> tuple[str, Path] | None:
    """Resolve the installation-registered Rooter Home as (home_id, real root).

    Returns None when the descriptor is unconfigured or has no rooter_home.
    Callers route wake/reminder by Home type instead of assuming a Project
    Session; this never fabricates a Rooter Home or its native-target store.
    """
    try:
        descriptor = load_installation_descriptor(installation_path)
    except InstallationProblem:
        return None
    if not descriptor.get("configured"):
        return None
    rooter_home = str(descriptor.get("rooter_home") or "").strip()
    if not rooter_home:
        return None
    root = Path(posix_windows_drive_locator(rooter_home)).expanduser()
    return ("rooter-001", root)


def _registry_authoritative_or_none(explicit_installation_file: str | None = None):
    """安装配置缺席（无描述文件）时返回 None：显式走既有桌面同 Project 合同。
    配置存在 → 返回 registry resolver；登记失败如实传播（不静默降级）。
    路径解析全部沿 paos_installation 既有服务工具，不在 CLI 里自建第二份
    安装/registry 目录判断。"""
    installation_path = resolve_installation_path(explicit_installation_file)
    if not installation_path.is_file():
        return None
    return lambda agent_id: resolve_home_by_registry(
        agent_id, installation_file=str(installation_path)
    )


def _parse_todo_update_sets(sets: list[str]) -> dict[str, Any]:
    """Parse repeatable `--set FIELD=VALUE` into a Current-field update dict.

    List fields (result_refs/context_refs) collect each value in order. A pair
    without `=` or an empty field name is an explicit usage error, not a guess.
    """
    updates: dict[str, Any] = {}
    for raw in sets or []:
        text = str(raw)
        if "=" not in text:
            raise CliError(
                f"--set 需要 FIELD=VALUE 形态：{text!r}",
                error_code="attention_todo_update_bad_pair",
            )
        name, value = text.split("=", 1)
        name = name.strip()
        if not name:
            raise CliError(
                f"--set 字段名不能为空：{text!r}",
                error_code="attention_todo_update_bad_pair",
            )
        if name in attention_todo_list_fields:
            updates.setdefault(name, []).append(value)
        else:
            updates[name] = value
    return updates


def _todo_write_receipt(write_result: dict[str, Any]) -> dict[str, Any]:
    """写回执精简（T-053 延续）：成功/错误仍如实，Home/路径/当前动作/任务计数
    可定位；完整 TODO 与任务正文仍由 show/orient 读，不把任务正文/历史当回执。
    服务层 write_home_todo 合同完整保留（全文仍真实写入）；不吞错误、不改
    写入事实、无新框架。"""
    todo = write_result.get("todo") or {}
    current = todo.get("current") or {}
    receipt = {
        "schema": write_result.get("schema"),
        "home": write_result.get("home"),
        "todo": {
            "schema": todo.get("schema"),
            "home_kind": todo.get("home_kind"),
            "home_id": todo.get("home_id"),
            "project_id": todo.get("project_id"),
            "current": {
                "stage": current.get("stage"),
                "next_action": current.get("next_action"),
            },
            "counts": todo.get("counts") or {},
        },
        "written_sha_tier": write_result.get("written_sha_tier"),
    }
    if "projection" in write_result:
        receipt["projection"] = write_result["projection"]
    return receipt


def execute_agent(
    args: argparse.Namespace,
    registry: ProjectRegistry,
    installation_path: Path | None = None,
) -> dict[str, Any]:
    """Agent-first durable communication (durable delivery + persisted intent only); an independent wake trigger is executed once by a legitimate native caller."""
    if args.agent_command == "resolve":
        return _resolve_agent_identity(
            str(args.identity), installation_path=installation_path)
    project = registry.read(args.project_id)
    root_raw = str(getattr(args, "root", None) or project.get("root_path") or "").strip()
    if not root_raw:
        raise CliError(
            "未提供 --root，且 Project 没有 root_path；无法定位 Agent activation state。",
            error_code="agent_activation_project_root_missing",
        )
    root = Path(posix_windows_drive_locator(root_raw)).expanduser()
    _resolve_staff_number_recipients(args)

    try:
        if args.agent_command == "send":
            frozen = resolve_recipients(
                project,
                recipients=list(args.to or []),
                broadcast=bool(args.broadcast),
                registry_lookup=resolve_home_by_registry,
            )
            invoked_members = {
                str(item.get("id") or "")
                for item in (project.get("sessions") or [])
                if isinstance(item, dict)
            }
            local_recipients = [value for value in frozen if value in invoked_members]
            cross_present = len(local_recipients) < len(frozen)
            # 统一 S 号/跨 Project 合同：任一 recipient 经 registry 定位出
            # 对方真实 Home 时走 Home 轴服务路径（逐 recipient 分流：本 Project
            # 工位直接投递+Notice，跨 Project/Rooter 走 registry 外投）；纯本
            # Project 维持原 v3/legacy 合同判断。
            send_remind = bool(getattr(args, "remind", False))
            mail_sender_id = str(args.sender_id or "")
            mail_subject = text_arg(args.subject, "mail subject", required=True)
            normal_delivered = set()
            if cross_present or _recipient_contract(root=root, recipients=local_recipients or frozen) == "v4":
                send_result = {
                    "ok": True,
                    **attention_send_mail_source(
                        installation_path=installation_path,
                        root=root,
                        project=project,
                        subject=mail_subject,
                        body=text_arg(args.body, "mail body"),
                        recipients=list(args.to or []),
                        broadcast=bool(args.broadcast),
                        sender_kind=str(args.sender_kind or "human"),
                        sender_id=mail_sender_id,
                        message_id=str(args.message_id or ""),
                        request_activation=True,
                    ),
                }
            else:
                send_result = {
                    "ok": True,
                    **send_agent_mail(
                        installation_path=installation_path,
                        root=root,
                        project=project,
                        subject=mail_subject,
                        body=text_arg(args.body, "mail body"),
                        recipients=list(args.to or []),
                        broadcast=bool(args.broadcast),
                        sender_kind=str(args.sender_kind or "human"),
                        sender_id=mail_sender_id,
                        message_id=str(args.message_id or ""),
                    ),
                }
            message_id_used = str((send_result.get("mail") or {}).get("message_id") or "")
            # **本次真实新投递集合**（S010 窄修 #2）：external_routes 中
            # `already_delivered` 是已收件的同 ID replay 件不进入再提醒集合。
            normal_delivered: set[str] = set()
            for entry in (send_result.get("mail") or {}).get("deliveries") or []:
                if isinstance(entry, dict):
                    agent_id = str(entry.get("recipient_agent_id") or "")
                    state_field = str(entry.get("state") or entry.get("delivery_state") or "")
                    if agent_id and state_field in {"delivered"}:
                        normal_delivered.add(agent_id)
            for route in (send_result.get("notices") or {}).get("external_routes") or []:
                if isinstance(route, dict):
                    mail_state = str(route.get("mail_state") or "")
                    if mail_state == "delivered":
                        normal_delivered.add(str(route.get("recipient") or ""))
                    # already_delivered → 已投递的 replay 件仅报告，不注入
            reminders: list[dict[str, Any]] = []
            if send_remind:
                reminders.extend(
                    _remind_via_native(
                        root=root,
                        project=project,
                        agent_id=agent_id,
                        message_id=message_id_used,
                        sender_id=mail_sender_id,
                        subject=mail_subject,
                        installation_path=installation_path,
                    )
                    for agent_id in sorted(normal_delivered)
                )
            confirmed_wake = any(r.get("accepted") is True for r in reminders)
            unknown_wake = any(r.get("state") in {"delivery_uncertain", "network_unconfirmed"} for r in reminders)
            send_result = {
                **send_result,
                "reminders": reminders,
                "runtime_wake_performed": True if confirmed_wake else None if unknown_wake else False,
            }
            # Short output semantics per S010（round-3）：
            #   - 普通 default agent send → 全部短回执（含已读取的 Notice 真实
            #     状态；无读端事实时是 not_observed），不把值硬编为 true。
            #   - --json: 完整机器字段（原 full 原件）。
            #   - --full-result: 原 full 原件。
            home_deliveries_list = sorted(
                normal_delivered
            )
            send_result.setdefault("home_deliveries", home_deliveries_list)
            projected = send_result.get("notices") or {}
            # Real Notice states only, from the two places the send actually
            # wrote them: same-Project dispatch items and cross-Project
            # external_routes (each route reports the state that its own
            # create_notice persisted). No guessing from Mail delivery and no
            # scanning other Homes.
            actual_notice_states = [
                str(item.get("state") or "")
                for item in projected.get("items") or []
                if isinstance(item, dict)
            ]
            actual_notice_states.extend(
                str(route.get("notice_state") or "")
                for route in projected.get("external_routes") or []
                if isinstance(route, dict)
            )
            if "pending" in actual_notice_states:
                pending_notice = "pending"
            elif "handled" in actual_notice_states:
                pending_notice = "handled"
            else:
                # replay 可能已 handled；未读到消费事实则 not_observed，不冒充。
                pending_notice = "not_observed"
            short_view = {
                "ok": send_result.get("ok"),
                "message_id": message_id_used,
                "home_deliveries": home_deliveries_list,
                "pending_notice": pending_notice,
                "reminders": reminders,
                "runtime_wake_performed": send_result["runtime_wake_performed"],
                "next_action": (
                    "native accepted → 等本人真实消费 Orientation/Current；"
                    "delivery_uncertain / network_unconfirmed → Mail 已落盘，原生未确认，不得重发或换路；"
                    "manual_required / native_rejected → 显式一次提醒未真实到达，"
                    "按 Contact 正常入口手动以同一 message_id 真实对接。"
                ),
            }
            argjson = bool(getattr(args, "json_output", False))
            fullresult = bool(getattr(args, "full_result", False))
            if fullresult or argjson:
                return send_result
            return {"ok": send_result.get("ok"), **short_view}

        if args.agent_command == "chat":
            target = str(args.to)
            cross_lookup = None
            if _recipient_contract(root=root, recipients=[target]) != "v4":
                # Same-project targets (legacy or not) keep the ORIGINAL
                # legacy path: only a genuinely cross-project recipient (not
                # a member of the invoked project) may attempt the lookup.
                invoked_members = {
                    str(i.get("id") or "")
                    for i in (project.get("sessions") or [])
                    if isinstance(i, dict)
                }
                if target not in invoked_members:
                    cross_lookup = _cross_project_target_lookup(
                        registry, root, target
                    )
            if cross_lookup is not None or _recipient_contract(root=root, recipients=[target]) == "v4":
                return {
                    "ok": True,
                    **attention_send_cat_source(
                        root=root,
                        project=project,
                        cat_base=str(args.cat_base or ""),
                        room_id=str(args.room),
                        target_agent_id=target,
                        content=text_arg(args.body, "CAT message body", required=True),
                        sender_agent_id=str(args.from_agent or ""),
                        message_id=str(args.message_id or ""),
                        reply_to=str(args.reply_to or ""),
                        request_activation=True,
                        target_project_lookup=cross_lookup,
                        installation_file=str(installation_path or ""),
                    ),
                }
            return {
                "ok": True,
                **send_cat_agent_message(
                    root=root,
                    project_id=args.project_id,
                    cat_base=str(args.cat_base or ""),
                    room_id=str(args.room),
                    target_agent_id=target,
                    content=text_arg(args.body, "CAT message body", required=True),
                    sender_agent_id=str(args.from_agent or ""),
                    message_id=str(args.message_id or ""),
                    reply_to=str(args.reply_to or ""),
                ),
            }

        if args.agent_command == "notify":
            if args.mail_message_id:
                source = dispatch_status(root, str(args.mail_message_id), installation_path=installation_path, project_id=args.project_id, registry_lookup=_registry_authoritative_or_none(getattr(args, "installation_file", None)))
                frozen = [
                    str(value)
                    for value in (source.get("recipients") or [])
                    if str(value or "").strip()
                ]
                selected = list(args.agents or []) or frozen
                if _recipient_contract(root=root, recipients=selected) == "v4":
                    return {
                        "ok": True,
                        **attention_request_mail_activation(
                            installation_path=installation_path,
                            root=root,
                            project=project,
                            message_id=str(args.mail_message_id),
                            agents=list(args.agents or []),
                            activation_request_id=str(
                                getattr(args, "activation_request_id", None) or ""
                            ),
                        ),
                    }
                return {
                    "ok": True,
                    **activate_mail_dispatch(
                        installation_path=installation_path,
                        root=root,
                        project_id=args.project_id,
                        message_id=str(args.mail_message_id),
                        agents=list(args.agents or []),
                    ),
                }

            if args.cat_exchange_ref:
                room_id, sep, exchange_id = str(args.cat_exchange_ref).partition(":")
                if not sep or not room_id or not exchange_id:
                    raise CliError(
                        "--cat-exchange 必须使用 <room-id>:<exchange-id>。",
                        error_code="cat_exchange_ref_invalid",
                    )
                selected = list(args.agents or [])
                if len(selected) > 1:
                    raise CliError(
                        "CAT Exchange 只能映射一个 target Agent；--agent 最多指定一次。",
                        error_code="cat_agent_selector_invalid",
                    )
                expected = selected[0] if selected else ""
                verified = verify_cat_exchange_source(
                    project_id=args.project_id,
                    cat_base=str(args.cat_base or ""),
                    room_id=room_id,
                    exchange_id=exchange_id,
                    expected_agent_id=expected,
                )
                target = str(verified.get("agent_id") or "")
                if _recipient_contract(root=root, recipients=[target]) == "v4":
                    return {
                        "ok": True,
                        **attention_request_cat_activation(
                            root=root,
                            project=project,
                            cat_base=str(args.cat_base or ""),
                            room_id=room_id,
                            exchange_id=exchange_id,
                            expected_agent_id=expected,
                            activation_request_id=str(
                                getattr(args, "activation_request_id", None) or ""
                            ),
                        ),
                    }
                return {
                    "ok": True,
                    **activate_cat_exchange(
                        root=root,
                        project_id=args.project_id,
                        cat_base=str(args.cat_base or ""),
                        room_id=room_id,
                        exchange_id=exchange_id,
                        expected_agent_id=expected,
                    ),
                }
    except (
        AgentActivationProblem,
        CatActivationProblem,
        AttentionServiceProblem,
        MailProblem,
        WorkstationProblem,
    ) as problem:
        raise CliError(
            str(problem),
            error_code=getattr(problem, "code", "agent_activation_error"),
            details=getattr(problem, "details", {}),
        ) from None

    raise CliError(
        f"Unsupported agent command: {args.agent_command}",
        error_code="unsupported_command",
    )


def execute_attention(
    args: argparse.Namespace,
    registry: ProjectRegistry,
    installation_path: Path,
) -> dict[str, Any]:
    """V1.3 Home service; public paths persist facts but never submit native turns."""
    recipient_aliases = None
    if args.attention_command != "history-read":
        if getattr(args, "agent_id", None):
            args.agent_id, recipient_aliases = _canonical_identity_and_aliases(
                str(args.agent_id), installation_path)
        _resolve_staff_number_recipients(args)
    try:
        if args.attention_command == "rooter-history-read":
            try:
                history = attention_read_history_input(
                    history_root=str(args.history_root),
                    agent_id=str(getattr(args, "home_id", "rooter-001") or "rooter-001"),
                    message_id=str(args.message_id or ""),
                    notice_id=str(args.notice_id or ""),
                )
            except (MailProblem, NoticeProblem) as problem:
                raise AttentionServiceProblem(
                    str(getattr(problem, "code", "attention_history_read_failed")),
                    str(problem),
                    dict(getattr(problem, "details", {}) or {}),
                ) from problem
            return {"ok": True, **history}

        if args.attention_command.startswith("rooter-"):
            home_ref = _registered_rooter_home(
                installation_path,
                home_id=str(getattr(args, "home_id", None) or "rooter-001"),
                require_todo_current=(args.attention_command != "rooter-todo-write"),
            )
            if args.attention_command == "rooter-show":
                result = {"ok": True, **attention_read_home_state(home_ref)}
                if getattr(args, "resume_owner", False):
                    result["receiver_preparation"] = _prepare_resume_receiver(installation_path, home_ref)
                return result
            if args.attention_command == "rooter-archive-input":
                return {
                    "ok": True,
                    **attention_archive_rooter_input(
                        home_ref=home_ref,
                        history_root=str(args.history_root),
                        message_id=str(args.message_id or ""),
                        notice_id=str(args.notice_id or ""),
                    ),
                }
            if args.attention_command == "rooter-read":
                return {
                    "ok": True,
                    **attention_mark_input_read(
                        home_ref=home_ref,
                        notice_id=str(args.notice_id),
                    ),
                }
            if args.attention_command == "rooter-handle":
                return {
                    "ok": True,
                    **attention_handle_input(
                        home_ref=home_ref,
                        notice_id=str(args.notice_id),
                        resolution=text_arg(args.resolution, "resolution"),
                        action_ref=text_arg(args.action_ref, "action ref"),
                    ),
                }
            if args.attention_command == "rooter-notice-update":
                return {
                    "ok": True,
                    **attention_organize_input(
                        home_ref=home_ref,
                        notice_id=str(args.notice_id),
                        summary=(
                            text_arg(args.summary, "notice summary", required=True)
                            if args.summary is not None
                            else None
                        ),
                        sort_order=args.sort_order,
                        archived=(
                            True if args.archive
                            else (False if args.restore else None)
                        ),
                        operation_id=str(args.operation_id or ""),
                    ),
                }
            if args.attention_command == "rooter-takeover":
                return {
                    "ok": True,
                    **attention_takeover_input(
                        home_ref=home_ref,
                        notice_id=str(args.notice_id),
                        updates=_parse_todo_update_sets(args.sets),
                        expected_fingerprint=getattr(args, "expected_fingerprint", None),
                    ),
                }
            if args.attention_command == "rooter-todo-update":
                return {
                    "ok": True,
                    **attention_update_home_todo_fields(
                        home_ref=home_ref,
                        updates=_parse_todo_update_sets(args.sets),
                        expected_fingerprint=getattr(
                            args, "expected_fingerprint", None
                        ),
                    ),
                }
            if args.attention_command == "rooter-todo-write":
                return {
                    "ok": True,
                    **_todo_write_receipt(
                        attention_write_home_todo(
                            home_ref=home_ref,
                            text=todo_text_arg(
                                args.body,
                                "TODO markdown",
                                required=True,
                            ),
                            expected_fingerprint=getattr(
                                args, "expected_fingerprint", None
                            ),
                        )
                    ),
                }
            if args.attention_command == "rooter-source-register":
                return {
                    "ok": True,
                    **attention_register_direct_input(
                        home_ref=home_ref,
                        source_ref=str(args.source_ref),
                        summary=text_arg(args.summary, "source summary", required=True),
                        request_activation=bool(args.activate),
                        activation_request_id=str(args.activation_request_id or ""),
                    ),
                }
            if args.attention_command == "rooter-source-status":
                return {
                    "ok": True,
                    **attention_read_source_status(
                        home_ref=home_ref,
                        source_kind=str(args.source_kind),
                        source_ref=str(args.source_ref),
                        installation_file=str(installation_path),
                    ),
                }

        if args.attention_command == "history-read":
            identity = str(args.agent_id)
            request = {"history_root": str(args.history_root),
                       "message_id": str(args.message_id or ""),
                       "notice_id": str(args.notice_id or "")}
            try:
                history = attention_read_history_input(agent_id=identity, **request)
            except (AttentionServiceProblem, MailProblem, NoticeProblem) as problem:
                if problem.code not in {"attention_history_home_missing", "mail_message_missing", "notice_missing"}:
                    raise
                try:
                    numbers = load_numbers(resolve_numbers_path(None, installation_path))
                except NumbersProblem as numbers_problem:
                    if numbers_problem.code == "agent_numbers_not_configured":
                        raise problem from numbers_problem
                    raise
                label = numbers.get(identity, identity)
                aliases = [home for home, number in numbers.items() if number == label]
                if len(aliases) > 1:
                    raise CliError(f"员工号 {label} 对应多个历史工位。",
                                   error_code="staff_number_ambiguous",
                                   details={"staff_number": label, "matches": aliases})
                alternate = label if identity != label else next(
                    (home for home in aliases if home != identity), None)
                if not alternate:
                    raise
                history = attention_read_history_input(agent_id=alternate, **request)
            return {"ok": True, **history}

        project = registry.read(args.project_id)
        root_raw = str(
            getattr(args, "root", None)
            or project.get("root_path")
            or ""
        ).strip()
        if not root_raw:
            raise CliError(
                "未提供 --root，且 Project 没有 root_path；无法定位 V1.3 Home。",
                error_code="attention_project_root_missing",
            )
        root = Path(posix_windows_drive_locator(root_raw)).expanduser()

        if args.attention_command in {
            "show",
            "handle",
            "read",
            "archive-input",
            "takeover",
            "notice-update",
            "todo-write",
            "todo-update",
            "source-register",
            "source-status",
        }:
            home_ref = attention_resolve_project_home(
                project=project,
                agent_id=args.agent_id,
                root_override=str(root),
                # 写口修复：旧 TODO 破损不能挡合法 v3 恢复载荷（真实 Home 定位
                # 保留，新载荷合同在 write_home_todo 校验）。todo-update 同理由
                # update_home_todo_fields 对坏/旧 TODO 给明确恢复写口引导。
                require_todo_current=(args.attention_command not in {"todo-write", "todo-update"}),
            )
            if args.attention_command == "show":
                return {"ok": True, **attention_read_home_state(home_ref)}
            if args.attention_command == "handle":
                handled = {"ok": True, **attention_handle_input(
                    home_ref=home_ref,
                    notice_id=str(args.notice_id),
                    resolution=text_arg(args.resolution, "resolution"),
                    action_ref=text_arg(args.action_ref, "action ref"),
                )}
                return handled
            if args.attention_command == "read":
                marked = {"ok": True, **attention_mark_input_read(
                    home_ref=home_ref,
                    notice_id=str(args.notice_id),
                    recipient_aliases=recipient_aliases,
                )}
                return marked
            if args.attention_command == "archive-input":
                return {
                    "ok": True,
                    **attention_archive_input(
                        home_ref=home_ref,
                        history_root=str(args.history_root),
                        message_id=str(args.message_id or ""),
                        notice_id=str(args.notice_id or ""),
                        recipient_aliases=recipient_aliases,
                    ),
                }
            if args.attention_command == "notice-update":
                return {
                    "ok": True,
                    **attention_organize_input(
                        home_ref=home_ref,
                        notice_id=str(args.notice_id),
                        summary=(
                            text_arg(args.summary, "notice summary", required=True)
                            if args.summary is not None
                            else None
                        ),
                        sort_order=args.sort_order,
                        archived=(
                            True if args.archive
                            else (False if args.restore else None)
                        ),
                        operation_id=str(args.operation_id or ""),
                    ),
                }
            if args.attention_command == "todo-write":
                return {
                    "ok": True,
                    **_todo_write_receipt(
                        attention_write_home_todo(
                            home_ref=home_ref,
                            text=todo_text_arg(
                                args.body,
                                "TODO markdown",
                                required=True,
                            ),
                            expected_fingerprint=getattr(
                                args, "expected_fingerprint", None
                            ),
                        )
                    ),
                }
            if args.attention_command == "takeover":
                return {
                    "ok": True,
                    **attention_takeover_input(
                        home_ref=home_ref,
                        notice_id=str(args.notice_id),
                        updates=_parse_todo_update_sets(args.sets),
                        expected_fingerprint=getattr(args, "expected_fingerprint", None),
                        recipient_aliases=recipient_aliases,
                    ),
                }
            if args.attention_command == "todo-update":
                return {
                    "ok": True,
                    **attention_update_home_todo_fields(
                        home_ref=home_ref,
                        updates=_parse_todo_update_sets(args.sets),
                        expected_fingerprint=getattr(
                            args, "expected_fingerprint", None
                        ),
                    ),
                }
            if args.attention_command == "source-register":
                return {
                    "ok": True,
                    **attention_register_direct_input(
                        home_ref=home_ref,
                        source_ref=str(args.source_ref),
                        summary=text_arg(args.summary, "source summary", required=True),
                        request_activation=bool(args.activate),
                        activation_request_id=str(args.activation_request_id or ""),
                    ),
                }
            return {
                "ok": True,
                **attention_read_source_status(
                    home_ref=home_ref,
                    source_kind=str(args.source_kind),
                    source_ref=str(args.source_ref),
                    installation_file=str(installation_path),
                ),
            }

        if args.attention_command == "send":
            return {
                "ok": True,
                **attention_send_mail_source(
                    installation_path=installation_path,
                    root=root,
                    project=project,
                    subject=text_arg(args.subject, "mail subject", required=True),
                    body=text_arg(args.body, "mail body"),
                    recipients=list(args.to or []),
                    broadcast=bool(args.broadcast),
                    sender_kind=str(args.sender_kind or "human"),
                    sender_id=str(args.sender_id or ""),
                    message_id=str(args.message_id or ""),
                    request_activation=bool(args.activate),
                ),
            }

        if args.attention_command == "notify":
            return {
                "ok": True,
                **attention_request_mail_activation(
                    installation_path=installation_path,
                    root=root,
                    project=project,
                    message_id=str(args.message_id),
                    agents=list(args.agents or []),
                    activation_request_id=str(args.activation_request_id or ""),
                ),
            }
    except AttentionServiceProblem as problem:
        raise CliError(
            str(problem),
            error_code=problem.code,
            details=problem.details,
        ) from None

    raise CliError(
        f"Unsupported attention command: {args.attention_command}",
        error_code="unsupported_command",
    )

DEFAULT_WAKE_PROMPT = "检查 Workstation mailbox 或 CAT，并从当前工位继续。"


def load_driver_config(path: str | None) -> dict[str, Any]:
    """Load an optional UTF-8 JSON config file used as native target details."""
    p_path = str(path or "").strip()
    if not p_path:
        return {}
    with open(p_path, "r", encoding="utf-8") as file_handle:
        data = json.loads(file_handle.read())
    if not isinstance(data, dict):
        raise CliError("driver-config JSON 必须是 object。", error_code="wake_driver_config_invalid")
    return data


def execute_wake(
    args: argparse.Namespace,
    registry: ProjectRegistry,
    installation_path: Path | None = None,
) -> dict[str, Any]:
    """Workless wake surface: native-target config + one-shot injection only.

    prepare-current prepares only the caller's registered Codex receiver.
    bind/unbind/status operate the Contact native-target store (no attempt
    machine); trigger calls the standalone native injection tool; probe/
    recover/stop/test are explicitly retired. The original reasons stay
    visible instead of silently becoming empty lists.

    Home-type routing: the installation-registered Rooter Home reads/writes
    only its own native-target store (no Project Session lookup or creation);
    Project Agents keep the existing path.
    """
    installation_path = installation_path or resolve_installation_path(
        getattr(args, "installation_file", None)
    )
    if getattr(args, "agent_id", None):
        args.agent_id = _canonical_identity_and_aliases(
            str(args.agent_id), installation_path)[0]
    if args.wake_command == "prepare-current":
        from codex_receiver_session_start import prepare_current
        from wakeup_native.codex_receiver import ReceiverError

        try:
            message = prepare_current()
        except (ReceiverError, InjectionError, KeyError) as problem:
            raise CliError(
                str(problem),
                error_code=getattr(problem, "code", "receiver_prepare_failed"),
            ) from None
        return {
            "ok": not message.startswith("receiver_prepare_skipped:"),
            "schema": "paos-wake-action/v1",
            "action": "prepare-current",
            "runtime": "codex",
            "systemMessage": message,
            "reminder_sent": False,
        }
    route = _rooter_home_root(installation_path)
    is_rooter_home = bool(route and args.agent_id == route[0])
    if is_rooter_home:
        root = route[1]
    else:
        project = registry.read(args.project_id)
        root_raw = str(getattr(args, "root", None) or project.get("root_path") or "").strip()
        if not root_raw:
            raise CliError(
                "未提供 --root，且 Project 没有 root_path；无法定位 Contact native-target。",
                error_code="wake_project_root_missing",
            )
        root = Path(posix_windows_drive_locator(root_raw)).expanduser()
    try:
        if args.wake_command == "bind":
            # Portable binding is explicit; never inherit a native session from
            # an old machine's Project JSON, even if historical fields remain.
            if not is_rooter_home:
                get_session_detail(registry, args.project_id, args.agent_id)
            native_session_id = str(args.native_session_id or "").strip()
            runtime_id = str(args.runtime_id or "").strip() or None
            if not native_session_id:
                raise CliError("bind 需要本机明确的 --native-session-id。",
                               error_code="wake_native_session_missing")
            driver_config = load_driver_config(args.driver_config)
            return {
                "ok": True,
                **bind_wakeup(installation_path=installation_path, root=root, project_id=None if is_rooter_home else args.project_id,
                              agent_id=args.agent_id, runtime_id=runtime_id,
                              native_session_id=native_session_id, driver_name=args.driver,
                              driver_config=driver_config),
            }
        if args.wake_command == "unbind":
            targets = load_native_targets(root, installation_path=installation_path) or {}
            if args.agent_id not in targets:
                return {
                    "ok": True,
                    "schema": "paos-wake-action/v1",
                    "action": "unbind",
                    "status": "not_configured",
                    "agent_id": args.agent_id,
                }
            targets.pop(args.agent_id, None)
            store_path = save_native_targets(root, targets, installation_path=installation_path)
            return {
                "ok": True,
                "schema": "paos-wake-action/v1",
                "action": "unbind",
                "status": "cleared",
                "agent_id": args.agent_id,
                "store": str(store_path),
            }
        if args.wake_command == "status":
            return {
                **runtime_contact(root, args.agent_id, installation_path=installation_path),
                "ok": True,
                "schema": "paos-wake-status/v1",
                "agent_id": args.agent_id,
                "activation": None,
                "native_turn": {"state": "not_observed"},
            }
        if args.wake_command == "probe":
            return {"ok": True, "schema": "paos-wake-action/v1", "action": "probe", "state": "retired", "note": "探测退役：不自动启动/探测 Harness，状态保持 unknown。"}
        if args.wake_command == "recover":
            return {"ok": True, "schema": "paos-wake-action/v1", "action": "recover", "state": "retired", "note": "恢复重试退役；如需提醒请走独立注入工具。"}
        if args.wake_command == "stop":
            targets = load_native_targets(root, installation_path=installation_path) or {}
            target = _native_target_for_home(targets, args.agent_id)
            if not target:
                return {"ok": True, "schema": "paos-wake-action/v1", "action": "stop", "state": "not_configured", "agent_id": args.agent_id}
            stop_file = str(target.get("stop_file") or "").strip()
            if not stop_file:
                result = {"ok": True, "schema": "paos-wake-action/v1", "action": "stop", "state": "no_stop_file", "agent_id": args.agent_id}
                if target.get("runtime") == "dsh":
                    result.update(
                        native_cancel_supported=False,
                        stop_effect="blocks_future_injections_only",
                        note="DSH STOP 只阻止后续注入；接收器不支持取消已运行回合。",
                    )
                return result
            Path(stop_file).parent.mkdir(parents=True, exist_ok=True)
            Path(stop_file).write_text("PAOS explicit stop marker\n", encoding="utf-8")
            result = {"ok": True, "schema": "paos-wake-action/v1", "action": "stop", "state": "stopped", "agent_id": args.agent_id, "stop_file": stop_file}
            if target.get("runtime") == "dsh":
                result.update(
                    native_cancel_supported=False,
                    stop_effect="blocks_future_injections_only",
                    note="DSH STOP 只阻止后续注入；接收器不支持取消已运行回合。",
                )
            return result
        if args.wake_command == "test":
            return {"ok": True, "schema": "paos-wake-action/v1", "action": "test", "state": "retired", "note": "试唤醒退役；不额外发模型测试请求。"}
        if args.wake_command == "trigger":
            message = text_arg(args.prompt, "wake prompt") or DEFAULT_WAKE_PROMPT
            native_model = None
            if getattr(args, "model", None):
                raw_model = str(args.model).strip()
                try:
                    parsed = json.loads(raw_model)
                except ValueError:
                    parsed = raw_model
                native_model = parsed  # opencode expects dict(providerID/modelID); others expect str
            target = _native_target_for_home(
                load_native_targets(root, installation_path=installation_path) or {}, args.agent_id,
                str(installation_path))
            if not isinstance(target, dict):
                return {
                    "ok": True,
                    "schema": "paos-wake-action/v1",
                    "action": "trigger",
                    "state": "not_configured",
                    "agent_id": args.agent_id,
                    "note": "未配置原生 target；原提醒不入注入通道。请用 paos wake bind 存储 Contact 还 native-targets.json 配置。",
                }
            try:
                receipt = native_inject(target=target, message=message, model=native_model)
            except InjectionUncertain as exc:
                return {
                    "ok": True,
                    "schema": "paos-wake-action/v1",
                    "action": "trigger",
                    "state": "delivery_uncertain",
                    "agent_id": args.agent_id,
                    "accepted": None,
                    "retry": False,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    **exc.details(),
                    "repair_owner": args.agent_id,
                }
            except (InjectionError, ValueError) as exc:
                return {
                    "ok": True,
                    "schema": "paos-wake-action/v1",
                    "action": "trigger",
                    "state": "native_rejected",
                    "agent_id": args.agent_id,
                    "accepted": False,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    **(exc.details() if isinstance(exc, InjectionError) else {}),
                    "repair_owner": (args.agent_id if exc.repair_owner == "target_owner" else exc.repair_owner) if isinstance(exc, InjectionError) else "sender",
                }
            return {
                "ok": True,
                "schema": "paos-wake-action/v1",
                "action": "trigger",
                "state": "accepted",
                "agent_id": args.agent_id,
                **receipt,
            }
    except CliError:
        raise
    except (InjectionError, WakeProblem, ValueError, OSError) as problem:
        raise CliError(
            f"Wake 命令失败：{problem}",
            error_code=getattr(problem, "code", "wake_operation_failed"),
            details={"detail": str(problem)},
        ) from None

    raise CliError(
        f"Unsupported wake command: {args.wake_command}",
        error_code="unsupported_command",
    )


def _canonical_identity_and_aliases(
    identity: str, installation_path: Path | None = None,
) -> tuple[str, set[str]]:
    """Return the current Home and the explicit old-source aliases for reads."""
    token = str(identity or "").strip()
    aliases = {token}
    try:
        ref = resolve_home_by_registry(
            token, installation_file=str(installation_path or "") or None)
    except (AttentionServiceProblem, HomeProblem) as problem:
        raise CliError(str(problem), error_code=problem.code,
                       details=problem.details) from problem
    canonical = str(ref["home_id"])
    aliases.add(canonical)
    # An exact old Home or Rooter input already carries its read alias. Only an
    # S input needs the reverse old-Home aliases for historical Mail metadata;
    # this keeps existing installations without an optional number config
    # working, while a present-but-broken config still raises.
    if token.upper().startswith("S") and token[1:].isdigit() and canonical == token:
        try:
            numbers = load_numbers(resolve_numbers_path(
                None, installation_path or Path(__file__).parent))
        except NumbersProblem as problem:
            if problem.code not in {
                "agent_numbers_not_configured", "agent_numbers_registry_missing",
            }:
                raise CliError(f"员工号登记不可用：{problem}",
                               error_code=problem.code,
                               details=problem.details) from problem
        else:
            aliases.update(key for key, value in numbers.items() if value == canonical)
    return canonical, aliases


def _cleanup_mail_result(result, args):
    if getattr(args, "cleanup_inputs", False):
        from paos_input_cleanup import cleanup_task
        result["cleanup"] = (cleanup_task(result["home"], result["task_id"], args.preserved_ref)
                             if result.get("task_state") == "done"
                             else {"complete": False, "state": "task_unfinished", "task_id": result["task_id"]})
    return result


def execute_mail(
    args: argparse.Namespace,
    registry: ProjectRegistry,
    installation_path: Path | None = None,
) -> dict[str, Any]:
    """V1.3 Mail UX backed by immutable Mail + unified Notice handling."""
    if getattr(args, "cleanup_inputs", False) and not str(getattr(args, "preserved_ref", "") or "").strip():
        raise ValueError("收尾清理需要 --preserved-ref，先归位有价值原件")
    original_agent_id = str(getattr(args, "agent_id", "") or "").strip()
    agent_aliases = {original_agent_id}
    if original_agent_id:
        args.agent_id, agent_aliases = _canonical_identity_and_aliases(
            original_agent_id, installation_path)
    if args.mail_command in {"rooter-claim", "rooter-result"}:
        home = _registered_rooter_home(
            installation_path or resolve_installation_path(
                getattr(args, "installation_file", None)))
        if args.mail_command == "rooter-claim":
            return {"ok": True, **claim_rooter_mail(
                home=home, message_id=str(args.message_id),
                task_id=str(getattr(args, "task", "") or ""),
                title=str(getattr(args, "title", "") or ""))}
        result = {"ok": True, **result_rooter_mail(
            home=home, message_id=str(args.message_id),
            result=text_arg(args.result, "mail result", required=True),
            task_id=str(getattr(args, "task", "") or ""),
            artifact_ref=str(getattr(args, "artifact_ref", "") or ""))}
        return _cleanup_mail_result(result, args)
    project = registry.read(args.project_id)
    root_raw = str(
        getattr(args, "root", None)
        or project.get("root_path")
        or ""
    ).strip()
    if not root_raw:
        raise CliError(
            "未提供 --root，且 Project 没有 root_path；无法定位 Workstation Mail。",
            error_code="mail_project_root_missing",
        )
    root = Path(posix_windows_drive_locator(root_raw)).expanduser()
    try:
        if args.mail_command == "claim":
            return {
                "ok": True,
                **claim_mail(
                    root=root, project=project, agent_id=str(args.agent_id),
                    message_id=str(args.message_id),
                    task_id=str(getattr(args, "task", "") or ""),
                    title=str(getattr(args, "title", "") or ""),
                    recipient_aliases=agent_aliases,
                ),
            }
        if args.mail_command == "result":
            result = {
                "ok": True,
                **result_mail(
                    root=root, project=project, agent_id=str(args.agent_id),
                    message_id=str(args.message_id),
                    result=text_arg(args.result, "mail result", required=True),
                    task_id=str(getattr(args, "task", "") or ""),
                    artifact_ref=str(getattr(args, "artifact_ref", "") or ""),
                    recipient_aliases=agent_aliases,
                ),
            }
            return _cleanup_mail_result(result, args)
        if args.mail_command == "send":
            if str(args.sender_kind or "human") == "agent" and args.sender_id:
                args.sender_id = _canonical_identity_and_aliases(
                    str(args.sender_id), installation_path)[0]
            args.to = [
                value if str(value).lower() == "human"
                else _canonical_identity_and_aliases(str(value), installation_path)[0]
                for value in (args.to or [])
            ]
            frozen = resolve_recipients(
                project,
                recipients=list(args.to or []),
                broadcast=bool(args.broadcast),
            )
            if _recipient_contract(root=root, recipients=frozen) == "v4":
                return {
                    "ok": True,
                    **attention_send_mail_source(
                        installation_path=installation_path,
                        root=root,
                        project=project,
                        subject=text_arg(args.subject, "mail subject", required=True),
                        body=text_arg(args.body, "mail body"),
                        recipients=list(args.to or []),
                        broadcast=bool(args.broadcast),
                        sender_kind=str(args.sender_kind or "human"),
                        sender_id=str(args.sender_id or ""),
                        message_id=str(args.message_id or ""),
                        request_activation=False,
                    ),
                }
            return {
                "ok": True,
                **send_mail(
                    installation_path=installation_path,
                    root=root,
                    project=project,
                    subject=text_arg(args.subject, "mail subject", required=True),
                    body=text_arg(args.body, "mail body"),
                    recipients=list(args.to or []),
                    broadcast=bool(args.broadcast),
                    sender_kind=str(args.sender_kind or "human"),
                    sender_id=str(args.sender_id or ""),
                    message_id=str(args.message_id or ""),
                ),
            }

        if args.mail_command == "reply":
            find_by_id(project.get("sessions", []), args.agent_id, "Agent")
            if not _home_uses_todo(root, args.agent_id):
                original = read_mail(root, args.agent_id, args.in_reply_to)
                metadata = original.get("metadata")
                if (
                    not isinstance(metadata, dict)
                    or metadata.get("recipient_agent_id") not in agent_aliases
                ):
                    raise CliError(
                        "被回复的 Mail 不属于该 Agent 的收件箱。",
                        error_code="mail_reply_source_mismatch",
                    )
                recipient_id = str(metadata.get("sender_id") or "").strip()
                if metadata.get("sender_kind") != "agent" or not recipient_id:
                    raise CliError(
                        "原 Mail 不是由 Project Agent 发送，无法通过 Agent Mail 回复。",
                        error_code="mail_reply_target_unavailable",
                        hint="对 Human 的正式请求请使用 paos session request-create。",
                    )
                recipient_id = _canonical_identity_and_aliases(
                    recipient_id, installation_path)[0]
                original_subject = str(metadata.get("subject") or "").strip()
                subject = text_arg(args.subject, "mail subject") or f"Re: {original_subject}"
                body = (
                    f"In reply to: `{args.in_reply_to}`\n\n"
                    + text_arg(args.body, "mail body", required=True)
                )
                reply = send_mail(
                    installation_path=installation_path,
                    root=root,
                    project=project,
                    subject=subject,
                    body=body,
                    recipients=[recipient_id],
                    sender_kind="agent",
                    sender_id=args.agent_id,
                    message_id=str(args.message_id or ""),
                )
                handling = mark_mail_handled(
                    root,
                    args.agent_id,
                    args.in_reply_to,
                    state="replied",
                    reason=f"Reply persisted as {reply['message_id']}",
                )
                try:
                    activation = activate_mail_dispatch(
                        installation_path=installation_path,
                        root=root,
                        project_id=args.project_id,
                        message_id=str(reply["message_id"]),
                    )
                except AgentActivationProblem as problem:
                    activation = {
                        "state": "activation_error",
                        "error_code": problem.code,
                        "detail": str(problem),
                    }
                return {
                    "ok": True,
                    **reply,
                    "handling": handling,
                    "activation": activation,
                }

            original = attention_read_project_mail_input(
                root=root,
                project=project,
                agent_id=args.agent_id,
                message_id=args.in_reply_to,
                recipient_aliases=agent_aliases,
            )
            original_mail = original.get("mail") or {}
            metadata = original_mail.get("metadata")
            if (
                not isinstance(metadata, dict)
                or metadata.get("recipient_agent_id") not in agent_aliases
            ):
                raise CliError(
                    "被回复的 Mail 不属于该 Agent 的收件箱。",
                    error_code="mail_reply_source_mismatch",
                )
            recipient_id = str(metadata.get("sender_id") or "").strip()
            if metadata.get("sender_kind") != "agent" or not recipient_id:
                raise CliError(
                    "原 Mail 不是由 Project Agent 发送，无法通过 Agent Mail 回复。",
                    error_code="mail_reply_target_unavailable",
                    hint="对 Human 的正式请求请使用 paos session request-create。",
                )
            recipient_id = _canonical_identity_and_aliases(
                recipient_id, installation_path)[0]
            recipient_home = resolve_home_by_registry(
                recipient_id, installation_file=getattr(args, "installation_file", None)
            )
            if recipient_home["home_kind"] == "rooter":
                attention_resolve_rooter_home(
                    home_path=recipient_home["home_path"], home_id=recipient_id
                )
            else:
                _recipient_contract(
                    root=Path(recipient_home["project_root"]), recipients=[recipient_id]
                )
            original_subject = str(metadata.get("subject") or "").strip()
            subject = text_arg(args.subject, "mail subject") or f"Re: {original_subject}"
            body = (
                f"In reply to: `{args.in_reply_to}`\n\n"
                + text_arg(args.body, "mail body", required=True)
            )
            reply = attention_send_mail_source(
                installation_path=installation_path,
                root=root,
                project=project,
                subject=subject,
                body=body,
                recipients=[recipient_id],
                sender_kind="agent",
                sender_id=args.agent_id,
                message_id=str(args.message_id or ""),
                request_activation=False,
            )
            notice = original["notice"]
            if notice["state"] == "handled" or notice.get("claimed"):
                handling = {"schema": ATTENTION_SERVICE_SCHEMA, "home": original["home"], "notice": notice}
            else:
                handling = attention_handle_mail_input(
                    root=root,
                    project=project,
                    agent_id=args.agent_id,
                    message_id=args.in_reply_to,
                    resolution="replied",
                    action_ref=str((reply.get("mail") or {}).get("message_id") or ""),
                    recipient_aliases=agent_aliases,
                )
            return {"ok": True, **reply, "handling": handling}

        if args.mail_command == "list":
            if _home_uses_todo(root, args.agent_id):
                return {
                    "ok": True,
                    **attention_list_project_mail_inputs(
                        root=root,
                        project=project,
                        agent_id=args.agent_id,
                    ),
                }
            return {"ok": True, **list_mail(root, args.agent_id)}

        if args.mail_command == "read":
            if _home_uses_todo(root, args.agent_id):
                result = attention_read_project_mail_input(
                    root=root,
                    project=project,
                    agent_id=args.agent_id,
                    message_id=args.message_id,
                    recipient_aliases=agent_aliases,
                )
                return {
                    "ok": True,
                    **(result.get("mail") or {}),
                    "notice": result.get("notice"),
                    "home": result.get("home"),
                }
            return {"ok": True, **read_mail(root, args.agent_id, args.message_id)}

        if args.mail_command == "handle":
            find_by_id(project.get("sessions", []), args.agent_id, "Agent")
            reason = text_arg(args.reason, "handling reason")
            if _home_uses_todo(root, args.agent_id):
                resolution = str(args.state or "handled")
                if reason:
                    resolution = f"{resolution}: {reason}"
                return {
                    "ok": True,
                    **attention_handle_mail_input(
                        root=root,
                        project=project,
                        agent_id=args.agent_id,
                        message_id=args.message_id,
                        resolution=resolution,
                        action_ref="",
                        recipient_aliases=agent_aliases,
                    ),
                }
            return {
                "ok": True,
                **mark_mail_handled(
                    root,
                    args.agent_id,
                    args.message_id,
                    state=args.state,
                    reason=reason,
                ),
            }

        if args.mail_command in {"status", "track", "task-status"}:
            installation_file = installation_path or resolve_installation_path(
                getattr(args, "installation_file", None))
            lookup = _registry_authoritative_or_none(installation_file)
            if args.mail_command == "status":
                return {"ok": True, **handoff_status(root, args.message_id, lookup, installation_file)}
            if lookup is None:
                raise CliError("Mail Task 需要当前安装的 Home 登记。", error_code="mail_tracking_home_required")
            home = lookup(args.agent_id)
            if args.mail_command == "track":
                return {"ok": True, **track_sent_mail(
                    root, args.project_id, args.message_id, home, args.task, lookup, installation_file,
                )}
            return {"ok": True, **sent_task_status(
                root, args.project_id, home, args.task, lookup, installation_file,
            )}
    except (MailProblem, AttentionServiceProblem, TodoProblem, NoticeProblem) as problem:
        raise CliError(
            str(problem),
            error_code=getattr(problem, "code", "mail_error"),
            details=getattr(problem, "details", {}),
        ) from None
    raise CliError(
        f"Unsupported mail command: {args.mail_command}",
        error_code="unsupported_command",
    )

def execute_library(
    args: argparse.Namespace,
    installation_path: Path,
    registry: ProjectRegistry,
) -> dict[str, Any]:
    """Workflow / Skill helpers share the same installed local roots."""
    try:
        if args.library_command == "search":
            roots = _load_roots(installation_path)
            return {"ok": True, **search_library_resources(roots, args.query,
                                                          kind=args.kind, limit=args.limit)}

        if args.library_command == "tools":
            roots = _load_roots(installation_path)
            path = _validate_tool_catalog_file(roots.get("tool_catalog") or "")
            text = Path(posix_windows_drive_locator(path)).read_text(encoding="utf-8")
            return {"ok": True, "path": path, "raw_markdown": text}
        if args.library_command == "roots":
            installation = load_installation_descriptor(installation_path)
            config_path = resolve_library_roots_path(
                installation=installation,
                explicit=args.roots_config,
            )
            if args.roots_command == "show":
                return {
                    "ok": True,
                    **load_library_roots(config_path),
                }
            result = register_library_roots(
                config_path,
                workflow_root=Path(str(args.workflow_root)).expanduser(),
                skill_root=Path(str(args.skill_root)).expanduser(),
                tool_catalog=getattr(args, "tool_catalog", None),
            )
            return {
                "ok": True,
                **result,
            }

        root = Path(posix_windows_drive_locator(str(args.root))).expanduser()
        if args.library_command == "init":
            result = (
                ensure_workflow_library(root)
                if args.kind == "workflow"
                else ensure_skill_library(root)
            )
            catalog = (
                refresh_workflow_catalog(root)
                if args.kind == "workflow"
                else refresh_skill_catalog(root)
            )
            return {
                "ok": True,
                "schema": "paos-library-init/v1",
                **result,
                "catalog": catalog,
            }

        if args.library_command == "catalog":
            catalog = (
                refresh_workflow_catalog(root)
                if args.kind == "workflow"
                else refresh_skill_catalog(root)
            )
            return {"ok": True, **catalog}

        if args.library_command == "skill-use":
            result = record_skill_use(
                root,
                skill_id=args.skill_id,
                score=float(args.score),
                project_id=str(args.project_id or ""),
                agent_id=str(args.agent_id or ""),
                work_id=str(args.work_id or ""),
                note=str(args.note or ""),
            )
            return {
                "ok": True,
                "schema": "paos-skill-use-recorded/v1",
                **result,
            }
    except (LibraryProblem, InstallationProblem) as problem:
        raise CliError(
            str(problem),
            error_code=getattr(problem, "code", "library_error"),
            details=problem.details,
        ) from None

    raise CliError(
        f"Unsupported library command: {args.library_command}",
        error_code="unsupported_command",
    )

def execute(
    args: argparse.Namespace,
    registry: ProjectRegistry,
    *,
    installation_path: Path | None = None,
) -> Any:
    resolved_installation_path = installation_path or resolve_installation_path(
        getattr(args, "installation_file", None)
    )
    creates_registration = args.command == "project" and args.project_command in {"register", "home-add"}
    creates_workstation = args.command == "workstation" and args.workstation_command == "init"
    reads_history = args.command == "attention" and args.attention_command == "history-read"
    if not (creates_registration or creates_workstation or reads_history):
        _resolve_staff_number_recipients(args)
        _validate_resolved_identity_subject(args, registry, resolved_installation_path)
    if args.command == "cat":
        return execute_cat(args, RestClient(args.url, service="CAT"), text_arg)


    if args.command == "install":
        try:
            if args.install_command == "configure":
                return {
                    "ok": True,
                    **write_installation_descriptor(
                        resolved_installation_path,
                        source_root=args.source_root,
                        library_roots_config=args.library_roots_config,
                        rooter_home=args.rooter_home,
                        data_root=args.data_root,
                    ),
                }
            descriptor = load_installation_descriptor(resolved_installation_path)
            if not descriptor["configured"]:
                return {"ok": True, **descriptor}
            source_runtime_path = Path(
                posix_windows_drive_locator(descriptor["source_root"])
            ).expanduser()
            try:
                data_root_path = effective_data_root(descriptor)
                if not data_root_path.is_dir():
                    raise InstallationProblem(
                        "installation_data_root_unavailable",
                        "登记的数据根不存在。",
                        {"data_root": str(data_root_path)},
                    )
            except InstallationProblem as problem:
                raise CliError(
                    str(problem), status=422, error_code=problem.code,
                    details=problem.details,
                ) from problem
            roots_path = resolve_library_roots_path(installation=descriptor)
            roots = load_library_roots(roots_path)
            rooter_home_raw = str(descriptor.get("rooter_home") or "").strip()
            rooter_home_path = (
                Path(posix_windows_drive_locator(rooter_home_raw)).expanduser()
                if rooter_home_raw
                else None
            )
            return {
                "ok": True,
                **descriptor,
                "source_root_exists": source_runtime_path.is_dir(),
                "data_root_exists": data_root_path.is_dir(),
                "rooter_home_exists": (
                    rooter_home_path.is_dir()
                    if rooter_home_path is not None
                    else False
                ),
                "library_roots": roots,
            }
        except (InstallationProblem, LibraryProblem) as problem:
            raise CliError(
                str(problem),
                error_code=getattr(problem, "code", "installation_error"),
                details=problem.details,
            ) from None

    if args.command == "workstation":
        return execute_workstation(args, registry, resolved_installation_path)
    if args.command == "data":
        return execute_data(args, resolved_installation_path)

    if args.command == "orient":
        return execute_orient(args, registry, resolved_installation_path)

    if args.command in {"context", "stage", "content"}:
        return execute_phase(args, resolved_installation_path, _resolve_agent_identity, RestClient)
    if args.command in {"team-plan", "task"}:
        return execute_team_actions(args, resolved_installation_path, _resolve_agent_identity, RestClient,text_arg)
    if args.command == "input-cleanup":
        return execute_cleanup(args, resolved_installation_path)

    if args.command == "status":
        return execute_status(args, registry, resolved_installation_path)

    if args.command == "inbox":
        return execute_inbox(args, registry)

    if args.command == "peers":
        return execute_peers(args, registry)

    if args.command == "team":
        return execute_team(args, registry)


    if args.command == "library":
        return execute_library(args, resolved_installation_path, registry)


    if args.command == "attention":
        return execute_attention(args, registry, resolved_installation_path)

    if args.command == "mail":
        return execute_mail(args, registry, resolved_installation_path)

    if args.command == "agent":
        return execute_agent(args, registry, resolved_installation_path)

    if args.command == "wake":
        return execute_wake(args, registry, resolved_installation_path)


    if args.command == "health":
        descriptor = load_installation_descriptor(resolved_installation_path)
        data = effective_data_root(descriptor)
        if not data.is_dir():
            raise CliError("安装 data_root 不存在。", error_code="installation_data_root_unavailable")
        return {"ok": True, "backend": "local_files", "installation": str(resolved_installation_path),
                "data_root": str(data), "http_service_required": False, "runtime_verified": False}


    if args.command == "project":
        if creates_registration:
            homes = ([args.home_id] if args.project_command == "home-add"
                     else [args.coordinator, *(args.home or ())])
            _validate_new_staff_homes(registry, args.project_id, homes, resolved_installation_path)
        if args.project_command == "register":
            result = registry.register(
                args.project_id, root_path=args.root,
                coordinator_home_id=args.coordinator,
                homes=args.home or (),
            )
            return {"ok": True, **result}
        if args.project_command == "home-add":
            return {"ok": True, **registry.add_home(
                args.project_id, args.home_id, expected_fingerprint=args.expected_fingerprint
            )}
        if args.project_command == "experience":
            project = registry.read_record(args.project_id)
            path = Path(posix_windows_drive_locator(project["root_path"])) / "Materials" / "TIPS.md"
            return {"ok": True, "path": str(path), "raw_markdown": path.read_text(encoding="utf-8")}
        # Project is a locator, not an alternative TODO / Human / progress model.
        return {"ok": True, "project": registry.read_record(args.project_id)}


    raise CliError("unsupported command", error_code="unsupported_command")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="paos",
        description=(
            "PAOS local Agent workbench: Home, Mail, Notice, Library and explicit native/CAT actions. Text values accept "
            "literal text, @FILE, or '-' for UTF-8 stdin (use @@... for a literal leading @)."
        ),
    )
    p.add_argument(
        "--installation-file",
        help="Override the installation descriptor path (default ~/.paos/installation.json)",
    )
    p.add_argument(
        "--library-roots-config",
        help="Pin the Library roots registry for this CLI invocation, overriding PAOS_LIBRARY_ROOTS_CONFIG",
    )
    p.add_argument(
        "--agent-numbers-file",
        help=(
            "Override the unique staff-number registry path (default: AgentNumBers locator from installation descriptor)"
        ),
    )
    p.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON, including structured errors",
    )
    p.add_argument(
        "--full-result",
        dest="full_result",
        action="store_true",
        default=None,
        help=(
            "Show the full Mail/CAT result instead of the compact default."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)
    add_phase_parsers(sub)
    add_data_parsers(sub)
    add_team_parsers(sub)
    add_cleanup_parser(sub)
    add_cat_parser(sub)

    sub.add_parser("health", help="Check local installation (not Runtime availability)")

    orient = sub.add_parser(
        "orient",
        help="Recover identity, current TODO, Mail and entry points",
    )
    orient.add_argument("project_id")
    orient.add_argument("agent_id")
    orient.add_argument("--root", help="Override Project root when root_path is missing")
    orientation = orient.add_mutually_exclusive_group()
    orientation.add_argument("--read", dest="read_originals", action="store_true",
                             help="Print the current Project AGENTS, Home AGENTS, INDEX, ENTRY and TODO source text")
    orientation.add_argument("--resume", dest="resume_owner", action="store_true",
                             help="Prepare your registered Codex receiver and read your recovery source text")

    status = sub.add_parser(
        "status",
        help="Show installation, current responsibility, contact and handoff evidence",
    )
    status.add_argument("project_id")
    status.add_argument("agent_id")
    status.add_argument("--root", help="Override Project root when root_path is missing")
    status.add_argument("--message-id", help="Inspect one outgoing durable Mail dispatch")

    inbox = sub.add_parser(
        "inbox",
        help="Read durable Workstation Mail and its Notice handling state",
    )
    inbox.add_argument("project_id")
    inbox.add_argument("agent_id")
    inbox.add_argument("--root", help="Override Project root when root_path is missing")

    attention = sub.add_parser(
        "attention",
        help="Local Home TODO/Notice/source operations; no inline native turn",
    )
    attention_sub = attention.add_subparsers(dest="attention_command", required=True)

    x = attention_sub.add_parser("show", help="Read one Project Agent Home TODO/NOTICE state")
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument("--root")

    x = attention_sub.add_parser("handle", help="Handle one Notice through the unified input state")
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument("notice_id")
    x.add_argument("--resolution")
    x.add_argument("--action-ref")
    x.add_argument("--root")

    x = attention_sub.add_parser(
        "read",
        help="Explicitly mark one Notice read; reading/listing alone never changes read state",
    )
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument("notice_id")
    x.add_argument("--root")

    x = attention_sub.add_parser(
        "archive-input",
        help=(
            "Move one already-read, handled Mail/Notice to an explicit external "
            "history batch; use history-read with that batch to read it back"
        ),
    )
    x.add_argument("project_id")
    x.add_argument("agent_id")
    target = x.add_mutually_exclusive_group(required=True)
    target.add_argument("--message-id", help="Archive Mail and its mapped Notice together")
    target.add_argument("--notice-id", help="Archive a non-Mail Notice and its sidecars")
    x.add_argument("--history-root", required=True, help="Absolute external batch directory")
    x.add_argument("--root")

    x = attention_sub.add_parser(
        "history-read",
        help=(
            "Read moved Mail/Notice from the explicit external batch supplied by "
            "the caller; archived IDs are not auto-discovered by active-mail reads"
        ),
    )
    x.add_argument("--history-root", required=True)
    x.add_argument("--agent-id", required=True)
    target = x.add_mutually_exclusive_group(required=True)
    target.add_argument("--message-id")
    target.add_argument("--notice-id")

    x = attention_sub.add_parser(
        "takeover",
        help=(
            "Read one Notice source, explicitly mark it read, then switch only "
            "the submitted Current fields of this exact Home"
        ),
    )
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument("notice_id")
    x.add_argument(
        "--set",
        dest="sets",
        action="append",
        default=[],
        metavar="FIELD=VALUE",
        help="Repeatable Current field update; at least one is required",
    )
    x.add_argument("--expected-fingerprint", help="Refuse if the TODO changed since this sha256")
    x.add_argument("--root")

    x = attention_sub.add_parser(
        "notice-update",
        help="Edit Notice summary/order/archive metadata without changing source or handling",
    )
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument("notice_id")
    x.add_argument("--summary", help="Edit Notice attention summary only; source body is unchanged")
    x.add_argument("--sort-order", type=int, help="Manual display order; lower values sort first")
    view = x.add_mutually_exclusive_group()
    view.add_argument(
        "--archive",
        action="store_true",
        help="Presentation-only archive; does not handle/cancel or clear activation intent",
    )
    view.add_argument(
        "--restore",
        action="store_true",
        help="Restore an archived Notice to the active presentation group",
    )
    x.add_argument("--operation-id", help="Stable idempotency key for this organize update")
    x.add_argument("--root")

    x = attention_sub.add_parser(
        "todo-write",
        help="Replace this exact Project Agent Home TODO v4 after identity validation",
    )
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument("--body", required=True, help="TODO Markdown, @FILE, or '-' for stdin")
    x.add_argument(
        "--expected-fingerprint",
        help="Optimistic lock: only write if the current TODO sha256 matches this value",
    )
    x.add_argument("--root")

    x = attention_sub.add_parser(
        "todo-update",
        help=(
            "Update only the named Current fields of this Home's one TODO v4; "
            "metadata, unmentioned Current fields and the whole Task body are kept"
        ),
    )
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument(
        "--set",
        dest="sets",
        action="append",
        default=[],
        metavar="FIELD=VALUE",
        help=(
            "Current: objective, next_action, waiting, inflight, updated_at, "
            "context_refs, result_refs. List refs: repeat --set key=value. "
            "Pinned and Tasks: use a fingerprint-guarded full todo-write."
        ),
    )
    x.add_argument(
        "--expected-fingerprint",
        help="Optimistic lock: only write if the current TODO sha256 matches this value",
    )
    x.add_argument("--root")

    x = attention_sub.add_parser(
        "source-register",
        help="Register one already-durable direct source for an exact Project Agent Home",
    )
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument(
        "--source-ref",
        required=True,
        help="Existing durable carrier locator: absolute/UNC path or http(s) URL",
    )
    x.add_argument("--summary", required=True, help="Short attention summary; not the body")
    x.add_argument("--activate", action="store_true")
    x.add_argument("--activation-request-id")
    x.add_argument("--root")

    x = attention_sub.add_parser(
        "source-status",
        help="Read Notice progress by stable source identity",
    )
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument("--source-kind", required=True, choices=["mail", "cat", "direct", "system"])
    x.add_argument("--source-ref", required=True)
    x.add_argument("--root")

    x = attention_sub.add_parser(
        "send",
        help="Persist Mail + Notice; optionally request activation without waking inline",
    )
    x.add_argument("project_id")
    recipients = x.add_mutually_exclusive_group(required=True)
    recipients.add_argument("--to", action="append", help="Global staff number Sxxx or exact Home id; repeatable")
    recipients.add_argument("--broadcast", action="store_true")
    x.add_argument("--subject", required=True)
    x.add_argument("--body", required=True, help=BODY_HELP)
    x.add_argument(
        "--sender-kind",
        default="human",
        choices=["human", "system", "coordinator", "agent", "external"],
    )
    x.add_argument("--sender-id", help="Global staff number Sxxx or exact sender Home id")
    x.add_argument("--message-id")
    x.add_argument(
        "--activate",
        action="store_true",
        help="Persist one activation intent (durable, no inline wake); a separate wake by a legitimate caller wakes the Runtime once",
    )
    x.add_argument("--root")

    x = attention_sub.add_parser(
        "notify",
        help="Persist one activation intent for an existing Mail source (durable; no inline wake — a separate legitimate caller trigger wakes the Runtime once)",
    )
    x.add_argument("project_id")
    x.add_argument("message_id")
    x.add_argument("--agent", dest="agents", action="append")
    x.add_argument("--activation-request-id")
    x.add_argument("--root")

    x = attention_sub.add_parser(
        "rooter-show",
        help="Read the registered Rooter Home without creating a Project Session",
    )
    x.add_argument("--home-id", default="rooter-001")
    x.add_argument("--resume", dest="resume_owner", action="store_true",
                   help="Prepare your registered Codex receiver during Rooter recovery")

    x = attention_sub.add_parser(
        "rooter-archive-input",
        help="Move one already-read, handled Rooter Mail/Notice to an external history batch",
    )
    target = x.add_mutually_exclusive_group(required=True)
    target.add_argument("--message-id")
    target.add_argument("--notice-id")
    x.add_argument("--history-root", required=True, help="Absolute external batch directory")
    x.add_argument("--home-id", default="rooter-001")

    x = attention_sub.add_parser(
        "rooter-history-read",
        help="Read moved Rooter input from the explicit external history batch",
    )
    x.add_argument("--history-root", required=True)
    target = x.add_mutually_exclusive_group(required=True)
    target.add_argument("--message-id")
    target.add_argument("--notice-id")
    x.add_argument("--home-id", default="rooter-001")

    x = attention_sub.add_parser(
        "rooter-read",
        help="Explicitly mark one Notice read in the registered Rooter Home",
    )
    x.add_argument("notice_id")
    x.add_argument("--home-id", default="rooter-001")

    x = attention_sub.add_parser(
        "rooter-handle",
        help="Handle one Notice in the registered Rooter Home",
    )
    x.add_argument("notice_id")
    x.add_argument("--resolution")
    x.add_argument("--action-ref")
    x.add_argument("--home-id", default="rooter-001")

    x = attention_sub.add_parser(
        "rooter-notice-update",
        help="Edit registered Rooter Notice summary/order/archive metadata",
    )
    x.add_argument("notice_id")
    x.add_argument("--summary", help="Edit Notice attention summary only; source body is unchanged")
    x.add_argument("--sort-order", type=int, help="Manual display order; lower values sort first")
    view = x.add_mutually_exclusive_group()
    view.add_argument(
        "--archive",
        action="store_true",
        help="Presentation-only archive; does not handle/cancel or clear activation intent",
    )
    view.add_argument(
        "--restore",
        action="store_true",
        help="Restore an archived Notice to the active presentation group",
    )
    x.add_argument("--operation-id", help="Stable idempotency key for this organize update")
    x.add_argument("--home-id", default="rooter-001")

    x = attention_sub.add_parser(
        "rooter-takeover",
        help="Take over one registered Rooter Notice and switch only submitted Current fields",
    )
    x.add_argument("notice_id")
    x.add_argument("--set", dest="sets", action="append", default=[], metavar="FIELD=VALUE")
    x.add_argument("--expected-fingerprint")
    x.add_argument("--home-id", default="rooter-001")

    x = attention_sub.add_parser(
        "rooter-todo-update",
        help=(
            "Update only the named Current fields of the registered Rooter Home's "
            "one TODO v4; metadata, unmentioned Current fields and the whole Task body are kept"
        ),
    )
    x.add_argument(
        "--set",
        dest="sets",
        action="append",
        default=[],
        metavar="FIELD=VALUE",
        help=(
            "Current: objective, next_action, waiting, inflight, updated_at, "
            "context_refs, result_refs. List refs: repeat --set key=value. "
            "Pinned and Tasks: use a fingerprint-guarded full todo-write."
        ),
    )
    x.add_argument(
        "--expected-fingerprint",
        help="Optimistic lock: only write if the current TODO sha256 matches this value",
    )
    x.add_argument("--home-id", default="rooter-001")

    x = attention_sub.add_parser(
        "rooter-todo-write",
        help="Replace registered Rooter TODO v4 after identity validation",
    )
    x.add_argument("--body", required=True, help="TODO Markdown, @FILE, or '-' for stdin")
    x.add_argument(
        "--expected-fingerprint",
        help="Optimistic lock: only write if the current TODO sha256 matches this value",
    )
    x.add_argument("--home-id", default="rooter-001")

    x = attention_sub.add_parser(
        "rooter-source-register",
        help="Register one already-durable direct source in the registered Rooter Home",
    )
    x.add_argument(
        "--source-ref",
        required=True,
        help="Existing durable carrier locator: absolute/UNC path or http(s) URL",
    )
    x.add_argument("--summary", required=True, help="Short attention summary; not the body")
    x.add_argument("--activate", action="store_true")
    x.add_argument("--activation-request-id")
    x.add_argument("--home-id", default="rooter-001")

    x = attention_sub.add_parser(
        "rooter-source-status",
        help="Read registered Rooter Notice progress by stable source identity",
    )
    x.add_argument("--source-kind", required=True, choices=["mail", "cat", "direct", "system"])
    x.add_argument("--source-ref", required=True)
    x.add_argument("--home-id", default="rooter-001")

    peers = sub.add_parser(
        "peers",
        help="Find registered Project colleagues (TEAM role, TODO) plus installation Rooter without probing",
        epilog="Example: paos peers 3002 S032; send via agent send 3002 --to S029, or --to S035 (Rooter). Read TEAM.md for roles not shown.",
    )
    peers.add_argument("project_id")
    peers.add_argument("agent_id")
    peers.add_argument("--root", help="Override Project root when root_path is missing")
    peers.add_argument("--probe", action="store_true", help="Compatibility no-op: no native probe is performed; runtime state remains unverified")
    peers.add_argument("--summary", action="store_true", help="Return the compact colleague summary without full task/input history")

    team = sub.add_parser(
        "team",
        help="Read registered Project team, TEAM roles and separately registered installation Rooter",
        epilog="Example: paos team 3002 S032; TEAM.md owns expertise; the installation Rooter is listed separately. Contact is not live availability.",
    )
    team.add_argument("project_id")
    team.add_argument("agent_id")
    team.add_argument("--root", help="Override Project root when root_path is missing")
    team.add_argument("--probe", action="store_true", help="Compatibility no-op: no native probe is performed; runtime state remains unverified")
    team.add_argument("--summary", action="store_true", help="Return the compact colleague summary without full task/input history")

    agent = sub.add_parser(
        "agent",
        help=(
            "Agent durable communication: Mail/CAT persists and records an activation intent; "
            "an explicit one-shot native reminder uses --remind"
        ),
    )
    agents = agent.add_subparsers(dest="agent_command", required=True)

    x = agents.add_parser(
        "resolve",
        help=("Read-only identity resolution for an independent CAT backend: "
              "old Home or Sxxx -> current home_id/project_id/home_kind"),
    )
    x.add_argument("identity", help="Historical Home id or current global staff number Sxxx")

    x = agents.add_parser(
        "send",
        help=(
            "Persist Workstation Mail to stable Agent(s). Default: durable delivery + activation "
            "intent only (no inline wake). With --remind: also send one native reminder via Contact/"
            "runtime_injection; no polling or retry."
        ),
        epilog=("Example: paos agent send 3002 --to S035 --sender-kind agent "
                "--sender-id S032 --subject '安装协助' --body @request.md "
                "--message-id unique-001 --remind. First positional Project is sender context; "
                "Sxxx is resolved through the installation staff registry; the target may be "
                "another Project or installation Rooter. Mail saved != reminder accepted != task completed."),
    )
    x.add_argument("project_id")
    recipients = x.add_mutually_exclusive_group(required=True)
    recipients.add_argument(
        "--to",
        action="append",
        help="Global staff number Sxxx or exact Home id; repeatable",
    )
    recipients.add_argument(
        "--broadcast",
        action="store_true",
        help="Freeze all non-historical Project Agents as the durable recipient set",
    )
    x.add_argument("--subject", required=True)
    x.add_argument(
        "--body",
        required=True,
        help=BODY_HELP,
    )
    x.add_argument(
        "--sender-kind",
        default="human",
        choices=["human", "system", "coordinator", "agent", "external"],
    )
    x.add_argument("--sender-id", help="Global staff number Sxxx or exact sender Home id")
    x.add_argument("--message-id", help="Stable idempotency key for the whole Agent message")
    x.add_argument(
        "--remind",
        action="store_true",
        help="显式一次原生提醒：Mail 持久投递后，按 Contact 与 runtime_injection 对每个正常投递 Home 一次性注入；不能注入如实 manual_required / native_rejected；不做后台轮询与重试器。",
    )
    x.add_argument("--root")

    x = agents.add_parser(
        "chat",
        help="Persist CAT Exchange and register a Notice activation intent; whether the target Runtime turns is decided by its own native loop",
    )
    x.add_argument("project_id")
    x.add_argument("--room", required=True, help="CAT Room id with activation_owner=paos")
    x.add_argument("--to", required=True, help="Global staff number Sxxx or exact Home id")
    x.add_argument("--body", required=True, help=CAT_BODY_HELP)
    x.add_argument("--from-agent", help="Stable sender Agent id; omit for human")
    x.add_argument("--message-id", help="Stable idempotency key for CAT send + Agent activation")
    x.add_argument("--reply-to", help="Optional exact CAT Exchange id being replied to")
    x.add_argument(
        "--cat-base",
        help="CAT origin; default CAT_BASE_URL or http://127.0.0.1:8770",
    )
    x.add_argument("--root")

    x = agents.add_parser(
        "notify",
        help="Notify stable Agent recipients from one already-persisted durable source",
    )
    x.add_argument("project_id")
    source = x.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--mail",
        dest="mail_message_id",
        help="Existing Workstation Mail message id; frozen recipients are reused",
    )
    source.add_argument(
        "--cat-exchange",
        dest="cat_exchange_ref",
        help="Existing CAT source as <room-id>:<exchange-id>",
    )
    x.add_argument(
        "--agent",
        dest="agents",
        action="append",
        help=(
            "Optional global staff number Sxxx or exact Home expected from the durable source. "
            "Repeatable for Mail; CAT accepts at most one."
        ),
    )
    x.add_argument(
        "--cat-base",
        help="CAT origin for --cat-exchange; default CAT_BASE_URL or http://127.0.0.1:8770",
    )
    x.add_argument(
        "--activation-request-id",
        help="Stable V1.3 activation intent id for safe retry; omit for a new explicit cycle",
    )
    x.add_argument("--root")

    wake = sub.add_parser(
        "wake",
        help="Native receiver preparation, Contact bind/status/unbind and one-shot reminders",
    )
    wakes = wake.add_subparsers(dest="wake_command", required=True)

    wakes.add_parser(
        "prepare-current",
        help="Prepare only this Codex Desktop Owner's registered receiver; reuse a healthy instance, send no reminder",
    )

    x = wakes.add_parser(
        "bind",
        help="Store the Contact native target (runtime/session/… from --driver-config) for one Agent",
    )
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument("--driver", required=True, help="原生 runtime 名（codex / opencode / workbuddy / antigravity / dsh）")
    x.add_argument("--runtime-id")
    x.add_argument("--native-session-id")
    x.add_argument(
        "--driver-config",
        help="Optional UTF-8 JSON file containing native target config (base_url/…)",
    )
    x.add_argument("--root")

    x = wakes.add_parser("status")
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument("--root")

    x = wakes.add_parser(
        "trigger",
        help="Send one reminder through the standalone native injection tool (no attempt machine)",
    )
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument("--prompt", help="Literal, @FILE or '-' inject message")
    x.add_argument("--source-kind", default="manual", choices=["manual", "system"])
    x.add_argument("--source-id")
    x.add_argument(
        "--model",
        help='Human-specified model only; omit to inherit the target model. OpenCode: JSON '
             '{"providerID":"opencode","modelID":"MODEL_ID"}; '
             'Codex/WorkBuddy: native model string.',
    )
    x.add_argument("--root")

    x = wakes.add_parser("unbind", help="Drop the Contact native target for one Agent")
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument("--root")

    mail = sub.add_parser(
        "mail",
        help="Durable Markdown mail in Project-local Agent Workstations",
    )
    mails = mail.add_subparsers(dest="mail_command", required=True)

    x = mails.add_parser("send", help="Persist targeted or broadcast Workstation Mail")
    x.add_argument("project_id")
    recipients = x.add_mutually_exclusive_group(required=True)
    recipients.add_argument("--to", action="append", help="Global staff number Sxxx or exact Home ID; repeatable")
    recipients.add_argument(
        "--broadcast",
        action="store_true",
        help="Freeze all non-historical Project Agents as the recipient set",
    )
    x.add_argument("--subject", required=True)
    x.add_argument(
        "--body",
        required=True,
        help=BODY_HELP,
    )
    x.add_argument(
        "--sender-kind",
        default="human",
        choices=["human", "system", "coordinator", "agent", "external"],
    )
    x.add_argument("--sender-id", help="Global staff number Sxxx or exact sender Home id")
    x.add_argument("--message-id", help="Stable idempotency key for retry")
    x.add_argument("--root")

    x = mails.add_parser(
        "claim",
        help="Quietly claim one Mail into this Agent's TODO and Notice",
        epilog=("Example: paos mail claim 3002 S032 mail-001 --task T-...; "
                "claim is quiet and idempotent; follow with mail result or a targeted reminder."),
    )
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument("message_id")
    x.add_argument("--task", help="Existing Task ID to link; omit to create one")
    x.add_argument("--title", help="Title when creating a new Task")

    x = mails.add_parser(
        "result",
        help="Record a result on the claimed Mail's Task and Notice",
    )
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument("message_id")
    x.add_argument("--result", required=True, help="One line up to 500 characters (literal, @FILE or -)")
    x.add_argument("--task", help="Task ID; omit to use the Task linked by claim")
    x.add_argument("--artifact-ref", help="Result artifact path or durable ref")

    x = mails.add_parser(
        "rooter-claim",
        help="Quietly claim one Mail in the installation Rooter Home",
    )
    x.add_argument("message_id")
    x.add_argument("--task", help="Existing Rooter Task ID to link")
    x.add_argument("--title", help="Title when creating a new Rooter Task")

    x = mails.add_parser(
        "rooter-result",
        help="Record a result on a claimed Rooter Mail Task",
    )
    x.add_argument("message_id")
    x.add_argument("--result", required=True, help="One line up to 500 characters (literal, @FILE or -)")
    x.add_argument("--task", help="Rooter Task ID; omit to use the linked Task")
    x.add_argument("--artifact-ref", help="Result artifact path or durable ref")

    for command in (mails.choices["result"], mails.choices["rooter-result"]):
        command.add_argument("--cleanup-inputs", action="store_true")
        command.add_argument("--preserved-ref", help="Where valuable original content has been preserved")

    x = mails.add_parser("reply", help="Reply to an Agent Mail in this Agent's inbox")
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument("in_reply_to")
    x.add_argument("--body", required=True, help=BODY_HELP)
    x.add_argument("--subject", help="Override the default Re: subject")
    x.add_argument("--message-id", help="Stable idempotency key for retry")
    x.add_argument("--root")

    x = mails.add_parser("list", help="List durable Markdown mail for one Agent")
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument("--root")

    x = mails.add_parser("read", help="Read one durable Markdown mail file")
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument("message_id")
    x.add_argument("--root")

    x = mails.add_parser("handle", help="Record that one received Mail was handled")
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument("message_id")
    x.add_argument("--state", choices=["handled", "incorporated"], default="handled")
    x.add_argument("--reason", help="Short reason for the handling marker")
    x.add_argument("--root")

    x = mails.add_parser(
        "status",
        help="Read delivery, claim and result for the original Mail",
    )
    x.add_argument("project_id")
    x.add_argument("message_id")
    x.add_argument("--root")

    x = mails.add_parser("track", help="Link a sent Mail to the sender's existing TODO Task")
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument("message_id")
    x.add_argument("--task", required=True, help="Existing Task ID")
    x.add_argument("--root")

    x = mails.add_parser("task-status", help="Read outstanding Mail for the sender's Task")
    x.add_argument("project_id")
    x.add_argument("agent_id")
    x.add_argument("task")
    x.add_argument("--root")

    lib = sub.add_parser(
        "library",
        help="Manage filesystem-only Workflow / Skill libraries",
    )
    libs = lib.add_subparsers(dest="library_command", required=True)

    for name in ("init", "catalog"):
        x = libs.add_parser(name)
        x.add_argument("kind", choices=["workflow", "skill"])
        x.add_argument("--root", required=True)

    x = libs.add_parser("tools", help="Read the registered local Tool Catalog (read-only)",
                        epilog="Catalog lists candidate tools, not proof that a tool is installed, authorized or callable.")

    x = libs.add_parser(
        "search",
        help="Find active Workflow/Skill source files in the registered Libraries",
        epilog="Example: paos library search '工程变更' --kind workflow. Open source_path (current runtime-readable file); source_locator is its stable registered location. Read the source before using it. For tools use: paos library tools.",
    )
    x.add_argument("query", help="1–200 character query; all distinct whitespace-separated terms must match")
    x.add_argument("--kind", choices=["all", "workflow", "skill"], default="all")
    x.add_argument("--limit", type=int, choices=range(1, 51), default=20)

    x = libs.add_parser(
        "skill-use",
        help="Record one Skill use and rebuild derived Skill catalog stats",
    )
    x.add_argument("--root", required=True)
    x.add_argument("--skill-id", required=True)
    x.add_argument("--score", required=True, choices=["0", "0.3", "0.5", "1"])
    x.add_argument("--project-id")
    x.add_argument("--agent-id")
    x.add_argument("--work-id")
    x.add_argument("--note")


    roots = libs.add_parser(
        "roots",
        help="Register/show canonical machine-local Workflow and Skill roots",
    )
    roots_sub = roots.add_subparsers(dest="roots_command", required=True)

    x = roots_sub.add_parser("show")
    x.add_argument("--config", dest="roots_config")

    x = roots_sub.add_parser("set")
    x.add_argument("--workflow-root", required=True)
    x.add_argument("--skill-root", required=True)
    x.add_argument("--tool-catalog", help="Absolute path to the registered paos-tool-catalog/v1 file")
    x.add_argument("--config", dest="roots_config")

    install = sub.add_parser(
        "install",
        help="Inspect or configure machine-local PAOS installation locators",
    )
    installs = install.add_subparsers(dest="install_command", required=True)
    installs.add_parser("show", help="Show the installation descriptor and Library registry state")
    x = installs.add_parser("configure", help="Write the machine-local installation descriptor")
    x.add_argument("--source-root", required=True)
    x.add_argument(
        "--data-root",
        help="Absolute installation data root; omit only to keep an existing registered value",
    )
    x.add_argument("--library-roots-config", required=True)
    x.add_argument(
        "--rooter-home",
        help="Optional absolute path of the registered installation-level Rooter Home",
    )

    pr = sub.add_parser("project", help="Read local project registration or project experience")
    prs = pr.add_subparsers(dest="project_command", required=True)
    x = prs.add_parser("register", help="Register one existing OB project root and Coordinator Home; never overwrite")
    x.add_argument("project_id")
    x.add_argument("--root", required=True, help="Existing absolute project vault directory")
    x.add_argument("--coordinator", required=True, help="Current Coordinator global staff number or Home ID, e.g. S010")
    x.add_argument("--home", action="append", help="Additional registered Home ID; repeatable")
    x = prs.add_parser("home-add", help="Append one Home to an existing registration; preserve root and Coordinator")
    x.add_argument("project_id")
    x.add_argument("home_id")
    x.add_argument("--expected-fingerprint", required=True, help="SHA-256 of the current registration file's raw bytes")
    for name in ("show", "experience"):
        x = prs.add_parser(name)
        x.add_argument("project_id")

    w = sub.add_parser("workstation", help="Create or read a registered fixed Home")
    ws = w.add_subparsers(dest="workstation_command", required=True)

    x = ws.add_parser(
        "init",
        help="Create or repair the stable Project-local Agent Workstation",
    )
    x.add_argument("project_id")
    x.add_argument("session_id")
    x.add_argument("--root")
    x.add_argument("--objective")
    x.add_argument("--workflow-library")
    x.add_argument(
        "--guide-root",
        help=(
            "Optional System/Guide directory; otherwise infer it only from the "
            "standard System/Core/code source layout. Never fall back to a Workflow Library."
        ),
    )
    x.add_argument(
        "--protocols-root",
        help="Retired; specify --guide-root instead (old directory must not be reused).",
    )
    x.add_argument("--entry-template", help="ENTRY 母本文件；标准 System 安装默认定位 Project-Template，独立源码须显式提供。")
    x.add_argument("--skill-library")

    x = ws.add_parser(
        "show",
        help="Read the stable Agent Workstation TODO and mailbox state",
    )
    x.add_argument("project_id")
    x.add_argument("session_id")
    x.add_argument("--root")

    x = ws.add_parser(
        "guide-diff",
        help="Compare one reviewed candidate GUIDE file against its canonical source",
    )
    x.add_argument("project_id")
    x.add_argument("session_id")
    x.add_argument("--candidate", required=True, help="Candidate GUIDE.md path")
    x.add_argument("--canonical", required=True, help="Canonical GUIDE.md path")
    x.add_argument("--root")
    return p


def render_plain_error(exc: CliError) -> str:
    lines = [f"ERROR [{exc.error_code or 'cli_error'}]: {exc}"]
    os_error = (exc.details or {}).get("os_error")
    if os_error:
        lines.append(f"CAUSE: {os_error}")
    for issue in (exc.details or {}).get("issues") or []:
        locator = issue.get("locator") or issue.get("path") or ""
        lines.append(
            f"- [{issue.get('kind') or 'item'}] {issue.get('raw') or locator}"
            f" -> {issue.get('reason') or 'unknown'}"
        )
    if exc.hint:
        lines.append(f"HINT: {exc.hint}")
    if exc.operation_id:
        lines.append(f"operation: {exc.operation_id}")
    if exc.revision is not None:
        lines.append(f"revision: {exc.revision}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """One invocation owns one resolved installation and error boundary.

    This resembles a C++ executable's ``main`` plus argument parser. Every
    domain exception is translated into a stable CLI error at this edge;
    library and writer functions stay independently unit-testable.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    installation_path = resolve_installation_path(args.installation_file)
    # All Home/Contact helpers use this one explicit installation, including
    # cross-project delivery. Scope is this invocation, restored for embedding.
    previous = os.environ.get("PAOS_INSTALLATION_FILE")
    previous_roots = os.environ.get("PAOS_LIBRARY_ROOTS_CONFIG")
    os.environ["PAOS_INSTALLATION_FILE"] = str(installation_path)
    # Generated ENTRY commands pin the selected registry for this invocation.
    # Other commands keep the pre-existing environment/installation priority.
    if args.library_roots_config:
        os.environ["PAOS_LIBRARY_ROOTS_CONFIG"] = str(
            Path(posix_windows_drive_locator(args.library_roots_config)).expanduser().resolve()
        )
    try:
        result = execute(args, ProjectRegistry(installation_path), installation_path=installation_path)
        print(result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if isinstance(result, dict) and result.get("ok") is False else 0
    except (CliError, RegistryProblem, InstallationProblem, LibraryProblem, NumbersProblem, WorkstationProblem,
            HomeProblem, MailProblem, NoticeProblem, AttentionServiceProblem, TodoProblem,
            SqliteError, OSError, ValueError) as exc:
        error = exc if isinstance(exc, CliError) else CliError(str(exc),
            error_code=getattr(exc, "code", "local_operation_failed"),
            details=getattr(exc, "details", {}))
        print(json.dumps(error.as_dict(), ensure_ascii=False) if args.json_output
              else render_plain_error(error), file=sys.stderr)
        return 1
    finally:
        if previous is None:
            os.environ.pop("PAOS_INSTALLATION_FILE", None)
        else:
            os.environ["PAOS_INSTALLATION_FILE"] = previous
        if args.library_roots_config:
            if previous_roots is None:
                os.environ.pop("PAOS_LIBRARY_ROOTS_CONFIG", None)
            else:
                os.environ["PAOS_LIBRARY_ROOTS_CONFIG"] = previous_roots


def _load_roots(installation_path):
    installation = load_installation_descriptor(installation_path)
    return load_library_roots(resolve_library_roots_path(installation=installation))


if __name__ == "__main__":
    raise SystemExit(main())
