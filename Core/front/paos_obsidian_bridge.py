#!/usr/bin/env python3
"""One-shot JSON bridge for the Obsidian project/CAT plugins.

No HTTP listener is started. The bridge resolves the current vault against the
installation registry, reuses the existing Board and frontend request map, and
returns one JSON response on stdout. It is deliberately stateless: files, CLI
writers, Mail/Notice and the CAT backend remain the facts.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlsplit

try:
    from .paos_front_server import (
        Board,
        BoardProblem,
        READ_ERRORS,
        dispatch_request,
        error_view,
        runtime_path,
    )
except ImportError:  # direct script execution from Core/front
    from paos_front_server import (  # type: ignore
        Board,
        BoardProblem,
        READ_ERRORS,
        dispatch_request,
        error_view,
        runtime_path,
    )


def _system_root(board: Board) -> Path:
    source = runtime_path(str(board.installation.get("source_root") or "")).resolve()
    return source.parents[2] if len(source.parents) >= 3 else source


def resolve_context(board: Board, vault_root: Path | str) -> dict:
    """Match the exact current vault; unknown vaults are never defaulted."""
    vault = Path(vault_root).expanduser().resolve()
    for record in board.projects():
        root = runtime_path(str(record.get("root_path") or "")).resolve()
        if vault == root:
            return {"kind": "project", "project": record.get("id") or "", "vault_root": str(vault),
                    "system_root": str(_system_root(board)), "cat_url": board.cat_url}
    system_root = _system_root(board)
    if vault == system_root:
        return {"kind": "system", "project": None, "vault_root": str(vault),
                "system_root": str(system_root), "cat_url": board.cat_url}
    raise BoardProblem(
        "vault_not_registered",
        f"当前 Obsidian 库未匹配任何登记 Project 或 System 根：{vault}",
    )


def _project_scope(board: Board, context: dict, method: str, path: str,
                   body: dict | None) -> tuple[str, dict]:
    """Keep a project plugin on its own current Home set."""
    if context.get("kind") != "project":
        return path, dict(body or {})
    project = str(context.get("project") or "")
    record = board.registry.read_record(project)
    homes = {str(item) for item in (record.get("homes") or [])}
    url = urlsplit(path)
    query = parse_qs(url.query, keep_blank_values=True)
    project_paths = {"/api/dashboard", "/api/layout", "/api/document",
                     "/api/collaboration", "/api/cat/rooms"}
    if url.path in project_paths:
        supplied = query.get("project", [])
        if supplied and supplied[0] and supplied[0] != project:
            raise BoardProblem("project_scope_mismatch", "当前项目插件不能读写另一个 Project。")
        query["project"] = [project]
    if url.path.startswith("/api/agent/"):
        home = unquote(url.path.rsplit("/", 1)[-1])
        if home not in homes:
            raise BoardProblem("project_scope_mismatch", "当前项目插件不能读取另一个 Project 的 Home。")
    new_path = url.path
    if query:
        new_path += "?" + urlencode(query, doseq=True)
    payload = dict(body or {})
    if str(method).upper() in {"POST", "PUT"}:
        supplied = str(payload.get("project") or "").strip()
        if supplied and supplied != project:
            raise BoardProblem("project_scope_mismatch", "当前项目插件不能写入另一个 Project。")
        if url.path in {"/api/layout", "/api/collaboration"}:
            payload["project"] = project
        if url.path == "/api/hint":
            if str(payload.get("agent_id") or "") not in homes:
                raise BoardProblem("project_scope_mismatch", "提示只能发给当前 Project 的登记成员。")
        if url.path in {"/api/room", "/api/collaboration"}:
            members = payload.get("members")
            if not isinstance(members, list) or any(str(item) not in homes for item in members):
                raise BoardProblem("project_scope_mismatch", "成员必须属于当前 Project。")
    return new_path, payload


def handle_request(board: Board, request: dict, *, vault_root: Path | str) -> tuple[int, dict]:
    """Return (status, JSON body) for one stdin request."""
    if not isinstance(request, dict):
        return 400, {"ok": False, "error": "请求必须是 JSON 对象。", "error_code": "bad_json"}
    method = str(request.get("method") or "").strip().upper()
    path = str(request.get("path") or "").strip()
    body = request.get("body")
    if not method or not path:
        return 400, {"ok": False, "error": "请求需要 method 与 path。", "error_code": "bad_request"}
    if body is not None and not isinstance(body, dict):
        return 400, {"ok": False, "error": "body 必须是 JSON 对象。", "error_code": "bad_json"}
    try:
        context = resolve_context(board, vault_root)
    except READ_ERRORS as exc:
        return 422, error_view(exc)
    if method == "GET" and urlsplit(path).path == "/api/obsidian/context":
        return 200, {"ok": True, **context}
    try:
        scoped_path, payload = _project_scope(board, context, method, path, body)
    except READ_ERRORS as exc:
        return 422, error_view(exc)
    return dispatch_request(board, method, scoped_path, payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation-file", type=Path,
                        default=Path.home() / ".paos" / "installation.json")
    parser.add_argument("--vault-root", type=Path, required=True)
    parser.add_argument("--cat-url", default="", help="Optional existing CAT backend URL")
    args = parser.parse_args(argv)
    try:
        board = Board(args.installation_file, cat_url=args.cat_url)
        request = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
        status, body = handle_request(board, request, vault_root=args.vault_root)
        print(json.dumps({"status": status, "body": body}, ensure_ascii=False))
        return 0
    except READ_ERRORS as exc:
        print(json.dumps({"status": 500, "body": error_view(exc)}, ensure_ascii=False))
        return 2
    except (ValueError, UnicodeError) as exc:
        print(json.dumps({"status": 400, "body": {"ok": False, "error": str(exc),
                                                   "error_code": "bad_json"}}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
