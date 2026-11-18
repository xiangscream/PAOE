"""One-shot Rooter migration: move one old Home to its registered Sxxx path.

Default is a read-only plan. `--execute` writes a before-state JSON, moves the
directory, updates its TODO identity and Contact locator, then switches the
Project registry. Rooter runs this while the affected Home is between writes.
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
import tempfile
from typing import Any

from paos_agent_numbers import NumbersProblem, load_numbers, resolve_numbers_path
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


def _encoded(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _replace(path: Path, value: bytes) -> None:
    stream = tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False)
    staged = Path(stream.name)
    try:
        with stream:
            stream.write(value)
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def _contact_change(path: Path, old_path: Path, new_path: Path) -> tuple[bytes | None, dict | None, list[str]]:
    try:
        original = path.read_bytes()
    except FileNotFoundError:
        return None, None, []
    targets = json.loads(original)
    if not isinstance(targets, dict):
        raise MigrationProblem("migration_contact_invalid", "现行 Contact 登记不是有效对象。", path=str(path))
    if new_path.name in targets:
        raise MigrationProblem("migration_contact_conflict", "新员工号已有 Contact 登记。", path=str(path))
    if old_path.name not in targets:
        return original, None, []
    target = targets.pop(old_path.name)
    if not isinstance(target, dict):
        raise MigrationProblem("migration_contact_invalid", "旧员工 Contact 登记不是有效对象。", path=str(path))
    targets[new_path.name] = target
    changed = []
    for fields, key, field_name in (
        (target, "stop_file", "stop_file"),
        (target.get("extension"), "receiver_runtime_file", "extension.receiver_runtime_file"),
    ):
        value = fields.get(key) if isinstance(fields, dict) else None
        if not isinstance(value, str) or not value:
            continue
        locator = Path(posix_windows_drive_locator(value))
        if locator.is_relative_to(old_path):
            fields[key] = str(new_path / locator.relative_to(old_path))
            changed.append(field_name)
    return original, targets, changed


def _todo_line(path: Path, expected: str) -> tuple[str, int, int]:
    text = path.read_bytes().decode("utf-8")
    header = text.split("---", 2)[1] if text.startswith("---") else ""
    match = re.search(r"(?m)^(home_id:[ \t]*)([\"']?)([^\"'\s]+)\2[ \t]*\r?$", header)
    if not match or match.group(3) != expected:
        raise MigrationProblem(
            "migration_todo_identity_mismatch",
            f"TODO home_id 不是 {expected}：{path}",
            path=str(path), expected=expected,
            actual=(match.group(3) if match else None),
        )
    start, end = match.span(3)
    return text, start + 3, end + 3


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
        todo_text, _, _ = _todo_line(todo_path, old_home)
    contact_path = root / "private-data" / "contact" / "native-targets.json"
    _, targets, changed = _contact_change(contact_path, old_path, new_path)
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
        "contact_path": str(contact_path) if targets is not None else "",
        "contact_updated_locators": changed,
        "docs_pending": [
            str(root / "TEAM.md"),
            str(new_path / "ENTRY.md"),
            str(new_path / "CONTACT.md"),
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
    todo_path = Path(plan_value["todo_path"]) if plan_value.get("todo_path") else None
    todo_text = None
    if todo_path is not None:
        todo_text, todo_start, todo_end = _todo_line(todo_path, old_home)
    contact_path = Path(plan_value["contact_path"]) if plan_value["contact_path"] else None
    contact_original, targets, fields = (None, None, [])
    if contact_path is not None:
        contact_original, targets, fields = _contact_change(contact_path, old_path, new_path)
        if targets is None or contact_original is None:
            raise MigrationProblem("migration_contact_changed", "Contact 登记已变化，请重新预览。", path=str(contact_path))
    contact_backup = before_state_path.with_name(before_state_path.name + ".contact-before.json") if contact_path else None
    before = {
        **plan_value,
        "schema": "paos-home-migration-before/v1",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "registry_sha256_before": plan_value["registry_fingerprint"],
        "todo_sha256_before": (_sha(todo_path) if todo_path else ""),
        "todo_original": todo_text,
        "contact_before_path": str(contact_backup) if contact_backup else "",
        "rollback": {
            "move": f"{new_path} -> {old_path}",
            "registry": f"{new_home} -> {old_home}",
            "todo": f"home_id {new_home} -> {old_home}",
        },
    }
    before_state_path.parent.mkdir(parents=True, exist_ok=True)
    with before_state_path.open("xb") as stream:
        stream.write(_encoded(before))
    if contact_backup is not None:
        with contact_backup.open("xb") as stream:
            stream.write(contact_original)
    moved = False
    contact_updated = False
    todo_updated = False
    try:
        old_path.rename(new_path)
        moved = True
        if todo_text is not None:
            new_todo = todo_text[:todo_start] + new_home + todo_text[todo_end:]
            _replace(new_path / "TODO.md", new_todo.encode("utf-8"))
            todo_updated = True
        if contact_path is not None:
            if contact_path.read_bytes() != contact_original:
                raise MigrationProblem("migration_contact_changed", "Contact 登记已变化，没有覆盖。", path=str(contact_path))
            _replace(contact_path, _encoded(targets))
            contact_updated = True
        result = registry.replace_home(
            project_id, old_home, new_home,
            expected_fingerprint=before["registry_sha256_before"],
        )
        return {
            "ok": True,
            "schema": "paos-home-migration-result/v1",
            "project_id": project_id,
            "old_home_id": old_home,
            "new_home_id": new_home,
            "old_path": str(old_path),
            "new_path": str(new_path),
            "moved": moved,
            "registry_replaced": True,
            "todo_updated": todo_updated,
            "contact_updated": contact_updated,
            "contact_updated_locators": fields,
            "before_state": str(before_state_path),
            "backup": result.get("backup", ""),
            "docs_pending": plan_value.get("docs_pending", []),
        }
    except (MigrationProblem, RegistryProblem, OSError) as problem:
        try:
            if contact_updated:
                _replace(contact_path, contact_original)
            if todo_updated:
                _replace(new_path / "TODO.md", todo_text.encode("utf-8"))
            if moved:
                new_path.rename(old_path)
        except OSError as restore_error:
            raise MigrationProblem(
                "migration_restore_failed", f"迁移失败：{problem}；恢复失败：{restore_error}",
                before_state=str(before_state_path),
            ) from restore_error
        raise MigrationProblem(
            "migration_execute_failed", f"迁移失败，当前工位已恢复：{problem}",
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
        if not args.before_state:
            parser.error("--execute requires --before-state outside the moving Home")
        before = Path(args.before_state).expanduser().resolve()
        if before.is_relative_to(Path(value["old_path"]).resolve()):
            parser.error("--before-state must be outside the moving Home")
        result = _execute(value, args.installation_file or None, before.resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (MigrationProblem, RegistryProblem, NumbersProblem, OSError, ValueError) as problem:
        print(json.dumps({
            "ok": False,
            "error_code": getattr(problem, "code", "migration_failed"),
            "error": str(problem),
            "details": getattr(problem, "details", {}),
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
