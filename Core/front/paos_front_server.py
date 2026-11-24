"""Optional board for Portable. Existing file readers and CLI own all facts.

Run with ``python portable.py serve`` after initializing this checkout. No Core,
WorkBuddy Python, fixed drive, background consumer or CAT data directory needed.
The visual board originates from S040's WorkBuddy prototype.
"""
from __future__ import annotations

import argparse
import json
import math
import mimetypes
import os
import re
from pathlib import Path
import subprocess
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

PACKAGE = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent
DIST = STATIC / "dist"
sys.path.insert(0, str(PACKAGE / "code" / "personal-agent-os" / "scripts"))

from paos_attention_service import AttentionServiceProblem, read_home_state, resolve_home_by_registry
from paos_home import HomeProblem, project_agent_home, rooter_home
from paos_installation import InstallationProblem, effective_data_root, load_installation_descriptor
from paos_library import LibraryProblem, load_library_roots, scan_skills, scan_workflows
from paos_registry import ProjectRegistry, RegistryProblem
from paos_workstation import posix_windows_drive_locator
from paos_agent_numbers import (NumbersProblem, agent_id_for_staff_number,
                                load_numbers, resolve_numbers_path, staff_number)


# Workbench assets must not depend on the host MIME database. Windows registries
# can map .js to text/plain; browsers then refuse the module/script.
STATIC_CONTENT_TYPES = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".map": "application/json",
}


def static_content_type(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in STATIC_CONTENT_TYPES:
        return STATIC_CONTENT_TYPES[suffix]
    return mimetypes.guess_type(name)[0] or "application/octet-stream"

class BoardProblem(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


READ_ERRORS = (BoardProblem, HomeProblem, AttentionServiceProblem, RegistryProblem,
               InstallationProblem, LibraryProblem, NumbersProblem, OSError, UnicodeError)


def error_view(error: Exception) -> dict:
    return {"ok": False, "error": str(error),
            "error_code": getattr(error, "code", type(error).__name__)}


def runtime_path(locator: str) -> Path:
    return Path(posix_windows_drive_locator(locator)).expanduser()


class Board:
    def __init__(self, installation_file: Path, *, cat_url: str = ""):
        self.installation_file = Path(installation_file).resolve()
        self.installation = load_installation_descriptor(self.installation_file)
        if not self.installation["configured"]:
            raise BoardProblem("installation_missing", "先运行 portable.py init，或显式指定已有安装描述。")
        self.registry = ProjectRegistry(self.installation_file)
        self.cat_url = cat_url

    def _legacy_home_aliases(self) -> dict[str, list[str]]:
        """Read-only old-Home aliases from the one staff registry, never guessed."""
        try:
            numbers = load_numbers(resolve_numbers_path(
                None, self.installation_file, self.installation))
        except NumbersProblem as problem:
            if problem.code == "agent_numbers_not_configured":
                return {}
            raise
        aliases: dict[str, list[str]] = {}
        for home_id, label in numbers.items():
            aliases.setdefault(str(label), []).append(str(home_id))
        return aliases

    def run_paos(self, args: list[str], *, input_text: str | None = None,
                 timeout: float | None = 90) -> dict:
        """One existing CLI invocation. Never infer success from missing output."""
        source = runtime_path(self.installation["source_root"])
        env = dict(os.environ, PAOS_INSTALLATION_FILE=str(self.installation_file),
                   PAOS_LIBRARY_ROOTS_CONFIG=self.installation["library_roots_config"],
                   PYTHONIOENCODING="utf-8")
        try:
            result = subprocess.run(
                [sys.executable, "-X", "utf8", str(source / "scripts" / "paos.py"),
                 "--installation-file", str(self.installation_file), "--json", "--full-result", *args],
                env=env, input=input_text, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error_code": "cli_result_unknown", "retry": False,
                    "error": "调用未及时返回，结果未知；请核原件，不自动重发。"}
        except OSError as exc:
            return {"ok": False, "error_code": "cli_start_failed", "phase": "process_start",
                    "error": str(exc), "error_type": type(exc).__name__, "retry": True}
        raw = result.stdout.strip() or result.stderr.strip()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "error_code": "cli_output_invalid", "returncode": result.returncode,
                    "error": raw or "CLI 未返回 JSON。"}
        if not isinstance(value, dict):
            return {"ok": False, "error_code": "cli_output_invalid", "error": "CLI 未返回对象。"}
        if result.returncode:
            value["ok"] = False
        return value

    def projects(self) -> list[dict]:
        directory = effective_data_root(self.installation) / "project-registry" / "projects"
        return [self.registry.read_record(path.stem) for path in sorted(directory.glob("*.json"))]

    def home(self, home_id: str) -> dict:
        if home_id == "rooter-001":
            locator = self.installation.get("rooter_home")
            if not locator:
                raise BoardProblem("rooter_unbound", "当前安装未绑定 Rooter 工位。")
            return rooter_home(home_path=runtime_path(locator))
        record = next((p for p in self.projects() if home_id in p["homes"]), None)
        if record is None:
            raise BoardProblem("home_not_registered", "此 Home 未在当前安装的项目中登记。")
        return project_agent_home(project=self.registry.read(record["id"]), agent_id=home_id)

    def agent(self, home_id: str) -> dict:
        ref = self.home(home_id)
        state = read_home_state(ref)
        todo = state["todo"]
        if (todo["home_id"], todo["home_kind"], todo["project_id"]) != (
                ref["home_id"], ref["home_kind"], ref["project_id"]):
            raise BoardProblem("todo_identity_mismatch", f"{home_id} 的 TODO 身份与登记不一致。")
        home = Path(ref["home_path"])
        mails = sorted((home / "mailbox").glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        current = todo["current"]
        row = {"ok": True, "id": home_id, "home_path": str(home), "project": ref["project_id"],
               **current, "tasks": todo["counts"], "task_items": todo["tasks"],
               "pending_notices": state["notices"]["pending_count"], "mail_total": len(mails),
               "todo": (home / "TODO.md").read_text(encoding="utf-8"),
               "entry": (home / "ENTRY.md").read_text(encoding="utf-8") if (home / "ENTRY.md").is_file() else "",
               "mails": [{"name": p.name, "preview": p.read_text(encoding="utf-8")[:600]} for p in mails[:6]],
               "docs": [p.name for p in home.glob("*.md") if p.name not in {"TODO.md", "ENTRY.md", "CONTACT.md", "STATUS.md"}]}
        if ref["home_kind"] == "project_agent":
            row.update(self._team_fields(ref["project_id"], home_id))
        return row

    def examples(self) -> dict:
        roots = load_library_roots(runtime_path(self.installation["library_roots_config"]))
        result = {"workflow": [], "skill": [], "tool": [], "skipped": [], "registered": roots["registered"]}
        if not roots["registered"]:
            return result
        for kind, scanner in (("workflow", scan_workflows), ("skill", scan_skills)):
            for item in scanner(runtime_path(roots[f"{kind}_root"]), skipped=result["skipped"]):
                if item["status"] == "active":
                    result[kind].append({**item, "kind": kind})
        if roots["tool_catalog"]:
            result["tool"].append({"id": "tool-catalog", "title": "本机工具目录（使用前核实实际入口）",
                                   "kind": "tool", "path": roots["tool_catalog"]})
        return result


    def team_info(self, project_id: str) -> dict:
        record = self.registry.read_record(project_id)
        root = runtime_path(record["root_path"])
        path = root / "TEAM.md"
        try:
            body = path.read_text(encoding="utf-8") if path.is_file() else ""
        except (OSError, UnicodeError) as exc:
            raise BoardProblem("team_unreadable", f"TEAM.md 无法读取：{path}") from exc
        members: dict[str, dict] = {}
        active = False
        current = None
        for line in body.splitlines():
            if line.startswith("## "):
                active = line.strip() == "## 当前成员"
                current = None
                continue
            if not active:
                continue
            if line.startswith("### "):
                candidate = line[4:].strip()
                if re.fullmatch(r"[Ss]\d+", candidate):
                    canonical = candidate.upper()
                    if canonical not in set(record.get("homes") or []):
                        candidate = agent_id_for_staff_number(
                            candidate, installation_path=self.installation_file,
                            installation=self.installation)
                    else:
                        candidate = canonical
                current = candidate
                members[candidate] = {}
                continue
            if current is None:
                continue
            match = re.match(r"^\s*-\s*([^：:]+)[：:]\s*(.*)$", line)
            if not match:
                continue
            key, value = match.group(1).strip(), match.group(2).strip()
            for label in ("成员状态", "职责", "职责/专长", "专长", "名称", "员工号", "个人介绍/专长"):
                if key == label:
                    members[current][key] = value
        return {"path": str(path), "body": body, "members": members}

    def _team_fields(self, project_id: str, home_id: str) -> dict:
        info = self.team_info(project_id)
        member = info["members"].get(home_id, {})
        status = member.get("成员状态") or "资料未补齐"
        paused = "暂停" in status or "不是当前执行者" in status
        number = staff_number(home_id, installation_path=self.installation_file, installation=self.installation) or ""
        return {
            "number": number,
            "name": member.get("名称") or number or "未编号",
            "role": member.get("职责") or member.get("职责/专长") or member.get("专长") or "",
            "description": member.get("个人介绍/专长", ""),
            "member_status": status,
            "registered": True,
            "can_contact": not paused,
            "team_path": info["path"],
        }

    def layout(self, project_id: str) -> dict:
        record = self.registry.read_record(project_id)
        path = runtime_path(record["root_path"]) / ".paos" / "ui" / "board.json"
        if not path.is_file():
            return {"ok": True, "project": record["id"],
                    "layout": {"nodes": {}, "viewport": {"x": 0, "y": 0, "zoom": 1}}}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise BoardProblem("layout_invalid", f"布局文件无法读取：{path}") from exc
        return {"ok": True, "project": record["id"], "layout": self._clean_layout(value)}

    def _clean_layout(self, value) -> dict:
        if not isinstance(value, dict):
            raise BoardProblem("layout_invalid", "布局必须是 JSON 对象。")
        raw_nodes = value.get("nodes", {})
        if not isinstance(raw_nodes, dict):
            raise BoardProblem("layout_invalid", "布局 nodes 必须是对象。")
        nodes = {}
        for home_id, point in raw_nodes.items():
            if not isinstance(home_id, str) or not isinstance(point, dict):
                raise BoardProblem("layout_invalid", "布局节点必须是 id→坐标对象。")
            x, y = point.get("x"), point.get("y")
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (x, y)):
                raise BoardProblem("layout_invalid", "布局坐标必须是有限数字。")
            nodes[home_id] = {"x": x, "y": y}
        raw_view = value.get("viewport", {})
        if not isinstance(raw_view, dict):
            raise BoardProblem("layout_invalid", "布局 viewport 必须是对象。")
        view = {"x": 0, "y": 0, "zoom": 1}
        for key in view:
            if key in raw_view:
                item = raw_view[key]
                if not isinstance(item, (int, float)) or isinstance(item, bool) or not math.isfinite(item):
                    raise BoardProblem("layout_invalid", "布局视口必须是有限数字。")
                view[key] = item
        if view["zoom"] <= 0:
            raise BoardProblem("layout_invalid", "布局 zoom 必须大于 0。")
        return {"nodes": nodes, "viewport": view}

    def save_layout(self, project_id: str, value) -> dict:
        record = self.registry.read_record(project_id)
        layout = self._clean_layout(value)
        root = runtime_path(record["root_path"])
        path = root / ".paos" / "ui" / "board.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temp.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(temp, path)
        except OSError as exc:
            raise BoardProblem("layout_write_failed", f"布局无法保存：{path}") from exc
        finally:
            if temp.exists():
                temp.unlink()
        return {"ok": True, "project": record["id"], "layout": layout}

    def resource(self, kind: str, resource_id: str) -> dict:
        for item in self.examples().get(kind, []):
            if str(item.get("id")) != resource_id:
                continue
            path = Path(str(item.get("path") or ""))
            try:
                body = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise BoardProblem("resource_unreadable", f"资源原件无法读取：{path}") from exc
            return {"ok": True, "resource": {
                "id": resource_id, "kind": kind, "title": item.get("title", ""),
                "path": str(path), "body": body,
            }}
        raise BoardProblem("resource_not_found", "资源不在当前已登记 Libraries 中。")

    def document(self, project_id: str, relative: str) -> dict:
        record = self.registry.read_record(project_id)
        root = runtime_path(record["root_path"]).resolve()
        relative = str(relative or "").strip()
        if not relative or Path(relative).is_absolute():
            raise BoardProblem("document_path_invalid", "文档路径必须是项目内相对路径。")
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise BoardProblem("document_path_escape", "文档路径不能离开项目根。") from exc
        if not path.is_file():
            raise BoardProblem("document_missing", "文档不存在。")
        if path.suffix.lower() not in {".md", ".txt", ".json"}:
            raise BoardProblem("document_type_invalid", "只支持 Markdown、文本或 JSON 原件。")
        try:
            body = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise BoardProblem("document_unreadable", "文档无法读取。") from exc
        return {"ok": True, "path": relative, "body": body}

    def _unknown_result(self, result: dict) -> bool:
        if result.get("ok"):
            return False
        # Only an explicit pre-submission failure or rejection permits a new send.
        definite = result.get("message_submitted") is False or \
            result.get("status") in {400, 404, 409, 422} or \
            result.get("error_code") in {"cat_not_configured", "cli_start_failed", "empty_body", "human_sender_only"}
        return not definite

    def _result_state(self, result: dict) -> str:
        if self._unknown_result(result):
            return "unknown"
        return "saved" if result.get("ok") else "failed"

    def _notification_view(self, result: dict, remind: bool) -> str:
        if not remind:
            return "not_requested"
        dispatch = str(result.get("dispatch") or "")
        if dispatch == "queued":
            return "queued"
        if dispatch == "skipped":
            return "not_requested"
        reminders = result.get("reminders", [])
        if reminders:
            flags = [item.get("accepted") for item in reminders]
            if all(flag is True for flag in flags):
                return "accepted"
            if any(flag is not None for flag in flags):
                return "partial"
        return "unknown"

    def _validate_members(self, members: list[str]) -> None:
        for member in members:
            ref = self.home(member)
            if ref["home_kind"] == "project_agent":
                fields = self._team_fields(ref["project_id"], member)
                if not fields["can_contact"]:
                    raise BoardProblem("member_paused", f"{member} 在 TEAM 中明确暂停，不能发起协作或提醒。")

    def _agent_summary(self, row: dict, legacy_aliases: dict[str, list[str]] | None = None) -> dict:
        summary = {"ok": row.get("ok"), "id": row.get("id"), "project": row.get("project"),
                   "objective": row.get("objective", ""), "next_action": row.get("next_action", ""),
                   "tasks": row.get("tasks", {}), "pending_notices": row.get("pending_notices", 0),
                   "mail_total": row.get("mail_total", 0)}
        for key in ("number", "name", "role", "description", "member_status", "registered", "can_contact", "team_path"):
            summary[key] = row.get(key, "" if key not in {"registered", "can_contact"} else False)
        aliases = legacy_aliases if legacy_aliases is not None else self._legacy_home_aliases()
        summary["staff_number"] = row.get("number", "") or ""
        summary["legacy_home_ids"] = aliases.get(str(summary["staff_number"]), [])
        if not row.get("ok"):
            summary.update({"error": row.get("error", ""), "error_code": row.get("error_code", "")})
        return summary

    def collaboration(self, payload: dict) -> dict:
        project_id = str(payload.get("project") or "")
        mode = str(payload.get("mode") or "")
        members = payload.get("members")
        topic = str(payload.get("topic") or "").strip()
        body = str(payload.get("body") or "").strip()
        message_id = str(payload.get("message_id") or f"ui-{uuid.uuid4().hex}")
        remind = bool(payload.get("remind", False))
        if mode not in {"chat", "mail"}:
            raise BoardProblem("collaboration_mode_invalid", "mode 必须是 chat 或 mail。")
        if not isinstance(members, list) or not all(isinstance(x, str) and x for x in members):
            raise BoardProblem("collaboration_members_invalid", "members 必须是成员 id 列表。")
        if mode == "chat" and len(members) < 2:
            raise BoardProblem("collaboration_members_invalid", "chat 至少需要两位成员。")
        if mode == "mail" and len(members) < 1:
            raise BoardProblem("collaboration_members_invalid", "mail 至少需要一位成员。")
        if not topic:
            raise BoardProblem("collaboration_topic_missing", "主题不能为空。")
        if not body:
            raise BoardProblem("collaboration_body_missing", "正文不能为空。")
        self._validate_members(members)
        if mode == "mail":
            args = ["agent", "send", project_id]
            for member in members:
                args += ["--to", member]
            args += ["--sender-kind", "human", "--sender-id", "human", "--subject", topic,
                     "--body", "-", "--message-id", message_id]
            if remind:
                args.append("--remind")
            result = self.run_paos(args, input_text=body)
            return {"ok": bool(result.get("ok")), "state": self._result_state(result),
                    "mode": mode, "phase": "send", "message_id": message_id,
                    "notification": self._notification_view(result, remind),
                    "detail": result.get("error", ""), "error_code": result.get("error_code", ""),
                    "result": result}
        room_id = str(payload.get("room_id") or "").strip()
        if room_id:
            shown = self.cat(["show", room_id])
            if not shown.get("ok"):
                return {"ok": False, "state": self._result_state(shown), "mode": mode,
                        "phase": "room", "message_id": message_id, "room_id": room_id,
                        "notification": self._notification_view(shown, remind),
                        "detail": shown.get("error", ""), "error_code": shown.get("error_code", ""),
                        "result": shown}
            room = shown["room"]
            if room["status"] != "open":
                raise BoardProblem("collaboration_room_closed", "已有房间已结束，不能继续发起协作。")
            ids = {member["home_id"] for member in room["members"]} - {"human"}
            if room["title"] != topic or not ids <= set(members):
                raise BoardProblem("collaboration_room_mismatch", "已有房间的主题或成员与本次协作不匹配。")
        else:
            created = self.cat(["create", "--title", topic])
            if not created.get("ok"):
                return {"ok": False, "state": self._result_state(created), "mode": mode,
                        "phase": "create", "message_id": message_id,
                        "notification": self._notification_view(created, remind),
                        "detail": created.get("error", ""), "error_code": created.get("error_code", ""),
                        "result": created}
            room_id = str((created.get("room") or {}).get("id") or "")
        labels = {person["id"]: person["name"] for person in self.people()}
        for member in members:
            joined = self.cat(["join", room_id, "--home", member, "--label", labels.get(member, member)])
            if not joined.get("ok"):
                join_state = "unknown" if self._unknown_result(joined) else "partial"
                return {"ok": False, "state": join_state,
                        "mode": mode, "phase": "join", "message_id": message_id, "room_id": room_id,
                        "notification": self._notification_view(joined, remind),
                        "detail": joined.get("error", ""), "error_code": joined.get("error_code", ""),
                        "result": joined}
        sent = self.send_message(room_id, "human", body, message_id, notify=remind)
        if sent.get("ok"):
            state = "saved"
        elif self._unknown_result(sent):
            state = "unknown"
        else:
            state = "partial"
        return {"ok": bool(sent.get("ok")), "state": state, "mode": mode, "phase": "send",
                "message_id": message_id, "room_id": room_id,
                "notification": self._notification_view(sent, remind),
                "detail": sent.get("error", ""), "error_code": sent.get("error_code", ""),
                "result": sent}

    def collaboration_status(self, project_id: str, mode: str, message_id: str, room_id: str = "") -> dict:
        self.registry.read_record(project_id)
        if mode not in {"mail", "chat"}:
            raise BoardProblem("collaboration_mode_invalid", "协作方式须为 chat 或 mail。")
        if mode == "mail":
            result = self.run_paos(["mail", "status", project_id, message_id])
            return {"ok": bool(result.get("ok")), "state": "saved" if result.get("ok") else (
                "not_found" if result.get("error_code") in {"mail_message_missing", "mail_missing", "mail_dispatch_missing"} else "unknown"),
                "mode": mode, "message_id": message_id, "detail": result.get("error", ""), "result": result}
        if not room_id:
            return {"ok": False, "state": "unknown", "mode": mode, "message_id": message_id,
                    "detail": "chat 需要已知 room_id 才能核对。", "result": {}}
        result = self.cat(["read", room_id, "--after", "0"])
        found = False
        for item in (result.get("messages") or []):
            if isinstance(item, dict) and str(item.get("id") or "") == message_id:
                found = True
                break
        state = "saved" if found else ("not_found" if result.get("ok") else "unknown")
        return {"ok": bool(result.get("ok")), "state": state, "mode": mode,
                "message_id": message_id, "room_id": room_id,
                "detail": result.get("error", ""), "result": result}

    def cat(self, args: list[str], *, input_text: str | None = None) -> dict:
        if not self.cat_url:
            return {"ok": False, "error_code": "cat_not_configured", "error": "CAT 未配置；工位文件功能仍可使用。"}
        return self.run_paos(["cat", "--url", self.cat_url, *args], input_text=input_text)

    def dashboard(self, project_id: str = "", *, include_cat: bool = True) -> dict:
        projects = self.projects()
        selected = self.registry.read_record(project_id) if project_id else (projects[0] if projects else None)
        agents = []
        legacy_aliases = self._legacy_home_aliases()
        if selected:
            for home_id in selected["homes"]:
                try:
                    agents.append(self._agent_summary(self.agent(home_id), legacy_aliases))
                except READ_ERRORS as exc:
                    agents.append({"id": home_id, "ok": False,
                                   "staff_number": home_id if str(home_id).startswith("S") else "",
                                   "legacy_home_ids": legacy_aliases.get(home_id, []),
                                   **error_view(exc)})
        if include_cat:
            rooms_result = self.cat(["list"]) if self.cat_url else self.cat([])
        else:
            # A project plugin must render files even when the optional CAT
            # backend is configured but offline. Rooms load only on explicit CAT.
            rooms_result = {"ok": True, "rooms": [], "deferred": True}
        rooms = rooms_result["rooms"] if rooms_result.get("ok") else []
        root = runtime_path(selected["root_path"]) if selected else None
        index = root / "INDEX.md" if root else None
        team = self.team_info(selected["id"]) if selected else {"path": "", "body": "", "members": {}}
        known = {str(item.get("id")) for item in agents}
        for home_id, member in team["members"].items():
            if home_id in known:
                continue
            status = member.get("成员状态") or "资料未补齐"
            agents.append({"ok": True, "id": home_id, "registered": False,
                           "number": member.get("员工号", ""), "name": member.get("名称") or "未编号",
                           "role": member.get("职责") or member.get("职责/专长") or "",
                           "description": member.get("个人介绍/专长", ""),
                           "member_status": status, "can_contact": False,
                           "team_path": team["path"]})
        return {"ok": True, "project": selected["id"] if selected else "",
                "coordinator": selected["coordinator_home_id"] if selected else "", "agents": agents,
                "team": {"path": team["path"], "body": team["body"]},
                "projects": [{"id": p["id"], "name": runtime_path(p["root_path"]).name} for p in projects],
                "index": index.read_text(encoding="utf-8") if index and index.is_file() else "",
                "examples": self.examples(), "rooms": rooms,
                "cat": ({**rooms_result} if rooms_result.get("deferred")
                        else {"ok": True}) if rooms_result.get("ok") else rooms_result}

    def rooms(self, project_id: str = "", home_id: str = "") -> dict:
        homes = None
        if project_id:
            record = self.registry.read_record(project_id)
            homes = set(record["homes"])
            aliases = self._legacy_home_aliases()
            for project_home in record["homes"]:
                number = staff_number(
                    project_home, installation_path=self.installation_file,
                    installation=self.installation) or ""
                homes.update(aliases.get(number, []))
        result = self.cat(["list", "--home", home_id] if home_id else ["list"])
        if not result.get("ok") or homes is None:
            return result
        related = []
        for room in result["rooms"]:
            seats = self.cat(["members", room["id"]])
            if not seats.get("ok"):
                return seats
            if any(member["home_id"] in homes for member in seats["members"]):
                related.append(room)
        return {**result, "rooms": related}

    def create_room(self, title: str, members: list[str], *, details: dict | None = None) -> dict:
        for member in members:
            self.home(member)
        labels = {person["id"]: person["name"] for person in self.people()}
        details = details or {}
        args = ["create", "--title", title, "--from", "human", "--owner",
                str(details.get("owner_id") or "human"), "--close-policy",
                str(details.get("close_policy") or "owner")]
        args.extend(self._context_args(details.get("task_context")))
        result = self.cat(args)
        if not result.get("ok"):
            return result
        room_id = result["room"]["id"]
        for member in members:
            joined = self.cat(["join", room_id, "--home", member, "--label", labels[member]])
            if not joined.get("ok"):
                return {**joined, "room_id": room_id, "phase": "join"}
        return {"ok": True, "room_id": room_id}

    def people(self) -> list[dict]:
        """Names come from registered Homes, staff numbers and TEAM originals.

        `id` is the canonical current Home. `legacy_home_ids` is a read-only
        alias list from the single AGENT-NUMBERS registry so old CAT room seats
        can resolve to the same S-numbered employee without a second map.
        """
        aliases = self._legacy_home_aliases()
        people = []
        for project in self.projects():
            for home_id in project["homes"]:
                fields = self._team_fields(project["id"], home_id)
                number, role = fields["number"], fields["role"]
                people.append({"id": home_id, "home_id": home_id,
                               "staff_number": number or "", "number": number or "",
                               "legacy_home_ids": aliases.get(number or "", []),
                               "role": role,
                               "name": (number or "未编号") + (" · " + role if role else ""),
                               "project": project["id"]})
        if self.installation.get("rooter_home"):
            number = staff_number("rooter-001", installation_path=self.installation_file, installation=self.installation)
            people.append({"id": "rooter-001", "home_id": "rooter-001",
                           "staff_number": number or "", "number": number or "",
                           "legacy_home_ids": aliases.get(number or "", []),
                           "role": "System 运行支持",
                           "name": "Rooter", "project": "System"})
        return people

    def room(self, room_id: str) -> dict:
        result = self.cat(["show", room_id])
        return {"ok": True, **result["room"]} if result.get("ok") else result

    def team_plan(self, owner: str, task: str, project: str) -> dict:
        if not owner or not task:
            raise BoardProblem("team_plan_input_missing", "请指定计划负责人和已有任务。")
        result = self.run_paos(["team-plan", "plan", owner, "--task", task])
        if result.get("ok"):
            _check_team_scope(project, result["plan"]["project"])
        return result

    def room_team(self, room_id: str, project: str) -> dict:
        if not self.cat_url:
            raise BoardProblem("cat_not_configured", "当前画板没有配置 CAT。")
        result = self.run_paos(["team-plan", "members", "--room", room_id, "--cat-url", self.cat_url])
        if result.get("error_code") == "not_dedicated_room":
            return {"ok": True, "room": room_id, "team": None, "cards": {}}
        if result.get("ok"):
            _check_team_scope(project, result["team"]["plan"]["project"])
        return result

    def confirm_team(self, payload: dict) -> dict:
        _human_sender(payload)
        if not self.cat_url:
            raise BoardProblem("cat_not_configured", "当前画板没有配置 CAT。")
        action = payload.get("action")
        ident = payload.get("receipt_id")
        subject = payload.get("input")
        if action not in ("open-plan", "approve-roles", "save-role", "accept-goal"):
            raise BoardProblem("team_action_unknown", "请选择相应的团队操作。")
        if not isinstance(ident, str) or not ident or not isinstance(subject, dict):
            raise BoardProblem("team_action_input_invalid", "请提供本次操作的编号和审阅对象。")
        project = payload.get("project")
        if project:
            if action == "open-plan":
                home = resolve_home_by_registry(str(subject.get("owner") or ""),
                                                installation_file=str(self.installation_file))
                _check_team_scope(project, home["project_id"])
            else:
                room = self.room(str(subject.get("room") or ""))
                if not room.get("ok"):
                    return room
                # The public room context is fixed by the approved plan. Core verifies each action.
                _check_team_scope(project, (room.get("task_context") or {}).get("project_id"))
        # Core displays the reviewed originals and applies the receipt on a real Human decision.
        return self.run_paos(["team-plan", "confirm", action, "--id", ident, "--input", "-",
                              "--cat-url", self.cat_url], input_text=json.dumps(subject, ensure_ascii=False),
                             timeout=None)

    @staticmethod
    def _context_args(context: dict | None) -> list[str]:
        if context is None:
            return []
        if not isinstance(context, dict):
            raise BoardProblem("task_context_invalid", "任务入口需要一组文本字段。")
        args = []
        for field in ("goal", "source_ref", "human_request_ref", "project_id", "index_path"):
            if field in context:
                if not isinstance(context[field], str):
                    raise BoardProblem("task_context_invalid", f"{field} 必须是文本。")
                args.extend(["--" + field.replace("_", "-"), context[field]])
        return args

    def preview_recipients(self, room_id: str, target_ids: list[str], *,
                           invite: bool = False, notify: bool | None = None) -> dict:
        args = ["preview", room_id, "--from", "human"]
        for target in target_ids:
            args.extend(["--mention", target])
        if invite:
            args.append("--invite")
        if notify is not None:
            if not isinstance(notify, bool):
                raise BoardProblem("notify_invalid", "提醒开关必须是布尔值。")
            args.append("--notify" if notify else "--no-notify")
        return self.cat(args)

    def room_progress(self, room_id: str, payload: dict) -> dict:
        # The page is Human's reader. Agent progress uses the same CLI from its Home.
        args = ["progress", room_id, "--home", "human"]
        if "presence" in payload:
            args.extend(["--presence", str(payload["presence"])])
        if "last_read_seq" in payload:
            value = payload["last_read_seq"]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise BoardProblem("invalid_cursor", "已读位置必须是非负整数。")
            args.extend(["--read-to", str(value)])
        return self.cat(args)

    def room_context(self, room_id: str, payload: dict) -> dict:
        args = ["context", room_id, "--from", "human"]
        if "owner_id" in payload:
            args.extend(["--owner", str(payload["owner_id"])])
        args.extend(self._context_args(payload.get("task_context")))
        return self.cat(args)

    def close_room(self, room_id: str, action: str) -> dict:
        return self.cat(["close", room_id, "--from", "human", "--action", action])

    def send_message(self, room_id: str, sender: str, body: str, message_id: str,
                     reply_to: str = "", notify: bool | None = None,
                     target_ids: list[str] | None = None, invite: bool = False) -> dict:
        joined = self.cat(["join", room_id, "--home", sender, "--label", "Human" if sender == "human" else sender])
        if not joined.get("ok"):
            return {**joined, "message_submitted": False}
        # Stdin preserves literal @mentions and long text without CLI @FILE semantics.
        args = ["send", room_id, "--from", sender, "--body", "-", "--message-id", message_id]
        if invite:
            args.append("--invite")
        if reply_to:
            args += ["--reply-to", reply_to]
        for target in target_ids or []:
            args.extend(["--mention", target])
        if notify is not None:
            args.append("--notify" if notify else "--no-notify")
        return self.cat(args, input_text=body)

    def hint(self, home_id: str, example: dict) -> dict:
        ref = self.home(home_id)
        if ref["home_kind"] != "project_agent":
            raise BoardProblem("project_home_required", "画板参考留信面向登记的项目成员；Rooter 使用安装级联络入口。")
        resources = self.examples()
        item = next((x for kind in ("workflow", "skill", "tool") for x in resources[kind]
                     if (x["id"], x["kind"]) == (example.get("id"), example.get("kind"))), None)
        if item is None:
            raise BoardProblem("example_not_found", "选择的库资源不在当前安装登记中。")
        return self.run_paos(["agent", "send", ref["project_id"], "--to", home_id,
                              "--sender-kind", "human", "--subject", f"方法参考：{item['title']}",
                              "--body", f"请按当前责任判断是否采用此参考。\n{item['title']}\n{item['path']}",
                              "--message-id", f"board-reference-{uuid.uuid4().hex}"])


def _human_sender(payload: dict) -> None:
    if payload.get("sender_id", "human") != "human" or payload.get("actor_id", "human") != "human":
        raise BoardProblem("human_sender_only", "此网页使用 Human 身份发言和确认。")


def _check_team_scope(project: str, actual: str) -> None:
    if project and project != actual:
        raise BoardProblem("project_scope_mismatch", "此团队计划属于其他 Project。")


def _target_ids(payload: dict) -> list[str]:
    targets = payload.get("target_ids", [])
    if not isinstance(targets, list) or not all(isinstance(value, str) and value.strip() for value in targets):
        raise BoardProblem("targets_invalid", "请选择员工号列表。")
    return targets


def dispatch_request(board: Board, method: str, path: str,
                     body: dict | None = None, *, defer_cat: bool = False) -> tuple[int, dict]:
    """Dispatch one existing frontend request without HTTP.

    The HTTP Handler and the Obsidian process bridge share this exact map so the
    two hosts cannot drift into separate writers. Streaming events are owned by
    the host and deliberately are not turned into request/response calls.
    """
    method = str(method or "").upper()
    url = urlsplit(str(path or ""))
    payload = body if isinstance(body, dict) else {}
    try:
        if method == "GET":
            parts = url.path.strip("/").split("/")
            if url.path == "/api/cat/rooms":
                query = parse_qs(url.query)
                value = board.rooms(query.get("project", [""])[0], query.get("home_id", [""])[0])
            elif url.path == "/api/team-plan":
                query = parse_qs(url.query)
                value = board.team_plan(query.get("owner", [""])[0], query.get("task", [""])[0],
                                        query.get("project", [""])[0])
            elif len(parts) == 4 and parts[:2] == ["api", "room"] and parts[3] == "team":
                value = board.room_team(unquote(parts[2]), parse_qs(url.query).get("project", [""])[0])
            elif url.path == "/api/cat/people":
                value = {"ok": True, "people": board.people()}
            elif len(parts) == 4 and parts[:2] == ["api", "room"] and parts[3] == "events":
                return 400, {"ok": False, "error": "实时流由宿主直连 CAT，不走单次进程桥。",
                             "error_code": "stream_not_supported"}
            elif len(parts) == 4 and parts[:2] == ["api", "room"] and parts[3] == "messages":
                try:
                    after = int(parse_qs(url.query).get("after", ["0"])[0])
                except ValueError as exc:
                    raise BoardProblem("invalid_cursor", "消息位置必须是整数。") from exc
                if after < 0:
                    raise BoardProblem("invalid_cursor", "消息位置不能为负数。")
                value = board.cat(["read", unquote(parts[2]), "--after", str(after)])
            elif len(parts) == 4 and parts[:2] == ["api", "room"] and parts[3] == "members":
                value = board.cat(["members", unquote(parts[2])])
            elif url.path == "/api/layout":
                value = board.layout(parse_qs(url.query).get("project", [""])[0])
            elif url.path == "/api/library/resource":
                query = parse_qs(url.query)
                value = board.resource(query.get("kind", [""])[0], query.get("id", [""])[0])
            elif url.path == "/api/document":
                query = parse_qs(url.query)
                value = board.document(query.get("project", [""])[0], query.get("path", [""])[0])
            elif url.path == "/api/collaboration":
                query = parse_qs(url.query)
                value = board.collaboration_status(
                    query.get("project", [""])[0], query.get("mode", [""])[0],
                    query.get("message_id", [""])[0], query.get("room_id", [""])[0])
            elif url.path == "/api/dashboard":
                value = board.dashboard(
                    parse_qs(url.query).get("project", [""])[0],
                    include_cat=not defer_cat)
            elif url.path.startswith("/api/agent/"):
                value = board.agent(unquote(url.path.rsplit("/", 1)[-1]))
            elif url.path.startswith("/api/room/"):
                value = board.room(unquote(url.path.rsplit("/", 1)[-1]))
            else:
                return 404, {"ok": False, "error": "未找到此入口。", "error_code": "not_found"}
            return 200, value
        if method == "POST":
            if url.path == "/api/team/confirm":
                value = board.confirm_team(payload)
            elif url.path == "/api/room":
                members = payload.get("members")
                if not isinstance(members, list) or len(members) < 2 or not all(isinstance(x, str) for x in members):
                    raise BoardProblem("members_invalid", "请选择至少两个登记工位。")
                _human_sender(payload)
                value = board.create_room(str(payload.get("title") or "画板沟通"), members, details=payload)
            elif url.path == "/api/hint":
                value = board.hint(str(payload.get("agent_id") or ""), payload.get("example") or {})
            elif url.path.startswith("/api/room/") and url.path.endswith("/message-preview"):
                _human_sender(payload)
                value = board.preview_recipients(unquote(url.path.rsplit("/", 2)[-2]),
                    _target_ids(payload), invite=payload.get("invite") is True, notify=payload.get("notify"))
            elif url.path.startswith("/api/room/") and url.path.endswith(("/message", "/invite")):
                _human_sender(payload)
                targets = _target_ids(payload)
                notify = payload.get("notify")
                if notify is not None and not isinstance(notify, bool):
                    raise BoardProblem("notify_invalid", "提醒开关必须是布尔值。")
                text = str(payload.get("body") or "").strip()
                if not text:
                    raise BoardProblem("empty_body", "请输入发言内容。")
                value = board.send_message(unquote(url.path.rsplit("/", 2)[-2]),
                                           "human", text,
                                           str(payload.get("message_id") or f"board-{uuid.uuid4().hex}"),
                                           str(payload.get("reply_to") or ""),
                                           notify, targets, invite=url.path.endswith("/invite") or payload.get("invite") is True)
            elif url.path.startswith("/api/room/") and url.path.endswith("/progress"):
                _human_sender(payload)
                if payload.get("home_id", "human") != "human":
                    raise BoardProblem("human_sender_only", "网页只记录 Human 本人的已读位置。")
                value = board.room_progress(unquote(url.path.rsplit("/", 2)[-2]), payload)
            elif url.path.startswith("/api/room/") and url.path.endswith("/context"):
                _human_sender(payload)
                value = board.room_context(unquote(url.path.rsplit("/", 2)[-2]), payload)
            elif url.path.startswith("/api/room/") and url.path.endswith("/close"):
                _human_sender(payload)
                value = board.close_room(unquote(url.path.rsplit("/", 2)[-2]),
                                        str(payload.get("action") or "request"))
            elif url.path == "/api/collaboration":
                value = board.collaboration(payload)
            else:
                return 404, {"ok": False, "error": "未找到此入口。", "error_code": "not_found"}
            return 200, value
        if method == "PUT":
            if url.path != "/api/layout":
                return 404, {"ok": False, "error": "未找到此入口。", "error_code": "not_found"}
            value = board.save_layout(str(payload.get("project") or ""), payload.get("layout"))
            return 200, value
        return 404, {"ok": False, "error": "未找到此入口。", "error_code": "not_found"}
    except READ_ERRORS as exc:
        return 422, error_view(exc)


class Handler(BaseHTTPRequestHandler):
    def _cat_events(self, room_id: str, after: str):
        origin = self.server.board.cat_url
        if not origin:
            self._json({"ok": False, "error_code": "cat_not_configured", "error": "CAT 未配置。"}, 503)
            return
        headers = {"Accept": "text/event-stream"}
        if self.headers.get("Last-Event-ID"):
            headers["Last-Event-ID"] = self.headers["Last-Event-ID"]
        request = Request(origin.rstrip("/") + "/api/rooms/" + quote(room_id, safe="") +
                          "/events?after=" + quote(after, safe=""), headers=headers)
        try:
            upstream = urlopen(request, timeout=35)
        except (HTTPError, URLError, OSError):
            self._json({"ok": False, "error_code": "cat_stream_unavailable",
                        "error": "CAT 实时接口尚不可用，请核配对的服务版本。"}, 503)
            return
        with upstream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                for line in upstream:
                    self.wfile.write(line)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
                self.close_connection = True

    def _json(self, value: dict, status: int = 200):
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _workbench_file(self, url) -> bool:
        if url.path == "/cat/":
            self.send_response(302)
            self.send_header("Location", "/cat" + ("?" + url.query if url.query else ""))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        page = url.path in {"/", "/index.html", "/cat"}
        if page:
            path = DIST / "index.html"
        elif url.path.startswith("/assets/"):
            path = (DIST / unquote(url.path.lstrip("/"))).resolve()
            try:
                path.relative_to((DIST / "assets").resolve())
            except ValueError:
                self._json({"ok": False, "error": "未找到页面资源。", "error_code": "not_found"}, 404)
                return True
        else:
            return False
        if not path.is_file():
            self._json({"ok": False, "error": "工作台页面资源缺失，请核安装包。" if page else "未找到页面资源。",
                        "error_code": "frontend_assets_missing" if page else "not_found"}, 503 if page else 404)
            return True
        data = path.read_bytes()
        content_type = static_content_type(path.name)
        self.send_response(200)
        self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)
        return True

    def do_GET(self):
        url = urlsplit(self.path)
        if self._workbench_file(url):
            return
        parts = url.path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "room"] and parts[3] == "events":
            self._cat_events(unquote(parts[2]), parse_qs(url.query).get("after", ["0"])[0])
            return
        status, value = dispatch_request(self.server.board, "GET", self.path)
        self._json(value, status)

    def do_POST(self):
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("请求必须为 JSON 对象。")
        except (ValueError, UnicodeError) as exc:
            self._json({"ok": False, "error": str(exc), "error_code": "bad_json"}, 400)
            return
        status, value = dispatch_request(self.server.board, "POST", self.path, payload)
        self._json(value, status)

    def do_PUT(self):
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("请求必须为 JSON 对象。")
        except (ValueError, UnicodeError) as exc:
            self._json({"ok": False, "error": str(exc), "error_code": "bad_json"}, 400)
            return
        status, value = dispatch_request(self.server.board, "PUT", self.path, payload)
        self._json(value, status)

    def log_message(self, fmt, *args):
        return


def make_server(board: Board, *, port: int = 8780) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.board = board
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--installation-file", type=Path, default=PACKAGE / "config/local/installation.json")
    parser.add_argument("--cat-url", default="", help="可选 CAT 地址；不配置不阻塞工位读取")
    args = parser.parse_args(argv)
    try:
        server = make_server(Board(args.installation_file, cat_url=args.cat_url), port=args.port)
    except READ_ERRORS as exc:
        print(json.dumps(error_view(exc), ensure_ascii=False), file=sys.stderr)
        return 2
    print(f"POE 工作台：http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
