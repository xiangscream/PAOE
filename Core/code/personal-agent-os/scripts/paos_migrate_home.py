"""One-shot Rooter migration: move one old Home to its registered Sxxx path.

Default is a read-only plan. `--execute` writes a before-state JSON, moves the
directory, updates the one Project registry and the TODO v4 `home_id` line.
It never rewrites Mail, Notice, ENTRY, TEAM, CAT rooms, native sessions or the
staff-number registry; those keep their original source identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

from paos_agent_numbers import load_numbers, resolve_numbers_path
from paos_installation import load_installation_descriptor, resolve_installation_path
from paos_registry import ProjectRegistry, RegistryProblem
from paos_workstation import posix_windows_drive_locator


class MigrationProblem(RuntimeError):
    def __init__(self, code: str, message: str, **details: Any):
        super().__init__(message)
        self.code = code
        self.details = details


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(root: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        files.append({
            "path": path.relative_to(root).as_posix(),
            "size": path.stat().st_size,
            "sha256": _sha(path),
        })
    return files


def _todo_line(path: Path, expected: str) -> tuple[str, re.Match[str]]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"(?m)^(home_id:\s*)([\"']?)([^\"'\s]+)\2\s*$", text)
    if not match or match.group(3) != expected:
        raise MigrationProblem(
            "migration_todo_identity_mismatch",
            f"TODO home_id 不是 {expected}：{path}",
            path=str(path), expected=expected,
            actual=(match.group(3) if match else None),
        )
    return text, match


def plan(project_id: str, old_home: str, new_home: str,
         installation_file: str | None) -> dict[str, Any]:
    installation = resolve_installation_path(installation_file)
    descriptor = load_installation_descriptor(installation)
    registry = ProjectRegistry(installation)
    record = registry.read_record(project_id)
    if old_home not in record["homes"]:
        raise MigrationProblem("migration_home_not_registered", "旧 Home 不在当前 Project 登记中。", old_home=old_home)
    if new_home in record["homes"]:
        raise MigrationProblem("migration_target_registered", "新 Home 已在当前 Project 登记中。", new_home=new_home)
    numbers = load_numbers(resolve_numbers_path(None, installation, descriptor))
    if numbers.get(old_home) != new_home:
        raise MigrationProblem(
            "migration_staff_mapping_mismatch",
            f"唯一号码表没有 {old_home} -> {new_home}。",
            old_home=old_home, new_home=new_home,
        )
    if new_home in numbers:
        raise MigrationProblem("migration_staff_key_conflict", "新 S 号已有独立 key，不能迁移成重复登记。", new_home=new_home)
    root = Path(posix_windows_drive_locator(record["root_path"])).expanduser()
    old_path = root / "Workstations" / old_home
    new_path = root / "Workstations" / new_home
    if not old_path.is_dir():
        raise MigrationProblem("migration_old_path_missing", "旧工位目录不存在。", path=str(old_path))
    if new_path.exists():
        raise MigrationProblem("migration_target_path_exists", "目标工位路径已存在。", path=str(new_path))
    registry_path = registry._path(project_id)
    todo_path = old_path / "TODO.md"
    todo_text = None
    if todo_path.is_file():
        todo_text, _ = _todo_line(todo_path, old_home)
    return {
        "ok": True,
        "schema": "paos-home-migration-plan/v1",
        "project_id": project_id,
        "old_home_id": old_home,
        "new_home_id": new_home,
        "old_path": str(old_path),
        "new_path": str(new_path),
        "registry_path": str(registry_path),
        "registry_fingerprint": _sha(registry_path),
        "todo_path": str(todo_path) if todo_text is not None else "",
        "todo_home_id": old_home if todo_text is not None else "",
        "file_count": len(_manifest(old_path)),
        "docs_pending": [
            str(root / "TEAM.md"),
            str(old_path / "ENTRY.md"),
            str(root / "CONTACT.md"),
        ],
        "execute_hint": f"rerun with --execute --before-state <new-json>",
    }


def _execute(plan_value: dict[str, Any], installation_file: str | None,
             before_state_path: Path) -> dict[str, Any]:
    installation = resolve_installation_path(installation_file)
    registry = ProjectRegistry(installation)
    project_id = str(plan_value["project_id"])
    old_home = str(plan_value["old_home_id"])
    new_home = str(plan_value["new_home_id"])
    old_path = Path(plan_value["old_path"])
    new_path = Path(plan_value["new_path"])
    registry_path = Path(plan_value["registry_path"])
    todo_path = Path(plan_value["todo_path"]) if plan_value.get("todo_path") else None
    todo_text = None
    if todo_path is not None:
        todo_text, todo_match = _todo_line(todo_path, old_home)
    before = {
        **plan_value,
        "schema": "paos-home-migration-before/v1",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "registry_sha256_before": _sha(registry_path),
        "todo_sha256_before": (_sha(todo_path) if todo_path else ""),
        "todo_original": todo_text,
        "files": _manifest(old_path),
        "rollback": {
            "move": f"{new_path} -> {old_path}",
            "registry": f"{new_home} -> {old_home}",
            "todo": f"home_id {new_home} -> {old_home}",
        },
    }
    before_state_path.parent.mkdir(parents=True, exist_ok=True)
    before_state_path.write_text(
        json.dumps(before, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    moved = False
    replaced = False
    try:
        old_path.rename(new_path)
        moved = True
        result = registry.replace_home(
            project_id, old_home, new_home,
            expected_fingerprint=before["registry_sha256_before"],
        )
        replaced = True
        todo_updated = False
        if todo_path is not None and todo_text is not None:
            new_todo = todo_text[:todo_match.start(3)] + new_home + todo_text[todo_match.end(3):]
            (new_path / "TODO.md").write_text(new_todo, encoding="utf-8")
            todo_updated = True
        return {
            "ok": True,
            "schema": "paos-home-migration-result/v1",
            "project_id": project_id,
            "old_home_id": old_home,
            "new_home_id": new_home,
            "old_path": str(old_path),
            "new_path": str(new_path),
            "moved": moved,
            "registry_replaced": replaced,
            "todo_updated": todo_updated,
            "before_state": str(before_state_path),
            "backup": result.get("backup", ""),
            "docs_pending": plan_value.get("docs_pending", []),
        }
    except Exception as problem:
        if replaced:
            try:
                registry.replace_home(
                    project_id, new_home, old_home,
                    expected_fingerprint=_sha(registry_path),
                )
            except Exception:
                pass
        if moved:
            try:
                new_path.rename(old_path)
            except Exception:
                pass
        raise MigrationProblem(
            "migration_execute_failed", f"迁移失败，已尝试回退：{problem}",
            before_state=str(before_state_path),
        ) from problem


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation-file", default=os.environ.get("PAOS_INSTALLATION_FILE", ""))
    parser.add_argument("--project", required=True)
    parser.add_argument("--old-home", required=True)
    parser.add_argument("--new-home", required=True)
    parser.add_argument("--before-state", default="")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        value = plan(args.project, args.old_home, args.new_home, args.installation_file or None)
        if not args.execute:
            print(json.dumps(value, ensure_ascii=False, indent=2))
            return 0
        before = Path(args.before_state).expanduser() if args.before_state else (
            Path(value["new_path"]).parent.parent / f".paos-migration-{args.old_home}-{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
        )
        result = _execute(value, args.installation_file or None, before.resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (MigrationProblem, RegistryProblem, OSError, ValueError) as problem:
        print(json.dumps({
            "ok": False,
            "error_code": getattr(problem, "code", "migration_failed"),
            "error": str(problem),
            "details": getattr(problem, "details", {}),
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
