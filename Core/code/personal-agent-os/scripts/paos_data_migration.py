"""Explicit migration for machine-owned stores into installation Data.

The plan is read-only. Execute first saves a complete before-state and copies
the old files, then publishes the merged Contact store and moves Mail dispatch
and UI preferences. Rollback uses that same before-state.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any

from paos_data_paths import (
    contact_store_path, data_root, mail_dispatch_dir, project_scope,
    rooter_scope, ui_board_path,
)
from paos_installation import load_installation_descriptor, resolve_installation_path
from paos_registry import ProjectRegistry


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _project_records(installation: Path) -> list[dict]:
    from paos_installation import effective_data_root
    registry = ProjectRegistry(installation)
    directory = (effective_data_root(load_installation_descriptor(installation))
                 / "project-registry" / "projects")
    return [registry.read_record(path.stem)
            for path in sorted(directory.glob("*.json"))]


def _rooter_home(installation: Path) -> Path | None:
    descriptor = load_installation_descriptor(installation)
    value = str(descriptor.get("rooter_home") or "").strip()
    return Path(value).expanduser() if value else None


def _contact_sources(installation: Path) -> list[tuple[str, Path]]:
    sources = []
    for record in _project_records(installation):
        root = Path(record["root_path"])
        path = root / "private-data" / "contact" / "native-targets.json"
        if path.is_file():
            sources.append((f"project-{record['id']}", path))
    rooter = _rooter_home(installation)
    if rooter:
        path = rooter / "private-data" / "contact" / "native-targets.json"
        if path.is_file():
            sources.append(("rooter", path))
    return sources


def _mail_sources(installation: Path) -> list[tuple[str, Path, Path]]:
    sources = []
    for record in _project_records(installation):
        root = Path(record["root_path"])
        old = root / ".paos" / "mail" / "dispatch"
        sources.append((project_scope(record["id"]), old,
                        mail_dispatch_dir(project_scope(record["id"]), installation)))
    rooter = _rooter_home(installation)
    if rooter:
        old = rooter / ".paos" / "mail" / "dispatch"
        sources.append((rooter_scope(), old, mail_dispatch_dir(rooter_scope(), installation)))
    return sources


def _ui_sources(installation: Path) -> list[tuple[str, Path, Path]]:
    sources = []
    for record in _project_records(installation):
        root = Path(record["root_path"])
        old = root / ".paos" / "ui" / "board.json"
        sources.append((project_scope(record["id"]), old,
                        ui_board_path(project_scope(record["id"]), installation)))
    rooter = _rooter_home(installation)
    if rooter:
        old = rooter / ".paos" / "ui" / "board.json"
        sources.append((rooter_scope(), old, ui_board_path(rooter_scope(), installation)))
    return sources


def plan(installation_path: str | Path) -> dict[str, Any]:
    installation = resolve_installation_path(str(installation_path))
    contacts = {}
    contact_sources = []
    contact_target = contact_store_path(installation)
    if contact_target.exists():
        raise ValueError(f"Contact target already exists: {contact_target}")
    for scope, path in _contact_sources(installation):
        value = _read_json(path)
        if not isinstance(value, dict):
            raise ValueError(f"Contact store is not an object: {path}")
        for key, target in value.items():
            if key in contacts and contacts[key] != target:
                raise ValueError(f"Contact key conflict: {key}")
            contacts[key] = target
        contact_sources.append({"scope": scope, "path": str(path), "sha256": _sha(path)})
    mail = []
    for scope, old, new in _mail_sources(installation):
        if new.exists():
            raise ValueError(f"Mail target already exists: {new}")
        mail.append({"scope": scope, "old": str(old), "new": str(new),
                     "files": len(list(old.glob("*")))})
    ui = []
    for scope, old, new in _ui_sources(installation):
        if new.exists():
            raise ValueError(f"UI target already exists: {new}")
        ui.append({"scope": scope, "old": str(old), "new": str(new),
                   "sha256": _sha(old) if old.exists() else None})
    return {
        "ok": True,
        "schema": "paos-data-migration-plan/v1",
        "installation": str(installation),
        "data_root": str(data_root(installation)),
        "contact_target": str(contact_store_path(installation)),
        "contact_sources": contact_sources,
        "contact_keys": sorted(contacts),
        "contact_routes": [
            {"scope": project_scope(r["id"]), "project_id": r["id"],
             "path": str(Path(r["root_path"]) / "private-data/contact/native-targets.json"),
             "homes": r["homes"]} for r in _project_records(installation)
        ] + ([{"scope": "rooter", "project_id": "", "path": str(_rooter_home(installation) / "private-data/contact/native-targets.json"),
               "homes": ["rooter-001"]}] if _rooter_home(installation) else []),
        "mail": mail,
        "ui": ui,
        "execute_hint": "rerun with execute and before_state",
    }


def execute(installation_path: str | Path, before_state: str | Path) -> dict[str, Any]:
    installation = resolve_installation_path(str(installation_path))
    before_path = Path(before_state).expanduser().resolve()
    if before_path.exists():
        before = _read_json(before_path)
        if before.get("installation") != str(installation) or before.get("schema") != "paos-data-migration-before/v1":
            raise ValueError("Migration receipt belongs to another installation")
        if before.get("state") in {"rolled_back", "rollback_prepared"}:
            raise ValueError("Migration has entered rollback; use a new migration after rollback finishes")
        return _finish_execute(before_path, before)
    value = plan(installation)
    moved = [Path(item[key]).resolve() for kind in ('mail', 'ui') for item in value[kind]
             for key in ('old', 'new')]
    fixed = [Path(value['contact_target']).resolve(),
             *(Path(item['path']).resolve() for item in value['contact_sources'])]
    if any(before_path == p or before_path.is_relative_to(p) for p in moved + fixed):
        raise ValueError('Migration receipt must be outside the stores being moved')
    backup = before_path.parent / f"{before_path.stem}.backup"
    if backup.exists():
        raise ValueError(f"Migration backup already exists: {backup}")
    backup.mkdir(parents=True)
    contacts = {}
    for source in value["contact_sources"]:
        path = Path(source["path"])
        target = backup / "contact" / source["scope"] / "native-targets.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        contacts.update(_read_json(path))
    mail_backups = []
    for item in value["mail"]:
        old = Path(item["old"])
        target = backup / "mail" / item["scope"]
        if old.exists():
            shutil.copytree(old, target)
        else:
            target.mkdir(parents=True)
        mail_backups.append({"scope": item["scope"], "old": item["old"],
                             "new": item["new"], "backup": str(target)})
    ui_backups = []
    for item in value["ui"]:
        old = Path(item["old"])
        target = backup / "ui" / item["scope"] / "board.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        if old.exists():
            shutil.copy2(old, target)
        ui_backups.append({"scope": item["scope"], "old": item["old"],
                           "new": item["new"], "backup": str(target)})
    before = {
        "schema": "paos-data-migration-before/v1",
        "installation": str(installation),
        "backup": str(backup),
        "plan": value,
        "contact": contacts,
        "mail": mail_backups,
        "ui": ui_backups,
        "state": "prepared",
    }
    before_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(before_path, before)
    return _finish_execute(before_path, before)


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.with_name(f".{path.name}.staging")
    stage.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(stage, path)


def _finish_execute(before_path, before):
    value = before["plan"]
    replay = before.get("state") == "executed"
    contact_target = Path(value["contact_target"])
    if replay:
        return {"ok": True, "schema": "paos-data-migration-result/v1", "before_state": str(before_path), "replayed": True}
    if contact_target.exists():
        if _read_json(contact_target) != before["contact"]:
            raise ValueError("Contact changed during incomplete migration; preserve it and inspect")
    else:
        _write_json(contact_target, before["contact"])
    for item in [*value["mail"], *value["ui"]]:
        old, new = Path(item["old"]), Path(item["new"])
        if old.exists() and new.exists():
            raise ValueError(f"Both old and Data store exist: {old}")
        if old.exists():
            new.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old), str(new))
    before["state"] = "executed"
    _write_json(before_path, before)
    return {"ok": True, "schema": "paos-data-migration-result/v1",
            "before_state": str(before_path), "backup": before["backup"], "replayed": False,
            "contact_target": str(contact_target),
            "mail_moved": len(value["mail"]), "ui_moved": len(value["ui"])}


def rollback(before_state: str | Path, *, installation_path=None) -> dict[str, Any]:
    path = Path(before_state).expanduser().resolve()
    before = _read_json(path)
    if before.get("schema") != "paos-data-migration-before/v1":
        raise ValueError("Not a machine-store migration receipt")
    if installation_path is not None and before['installation'] != str(resolve_installation_path(str(installation_path))):
        raise ValueError('Rollback receipt belongs to another installation')
    if before.get("state") == "rolled_back":
        return {"ok": True, "schema": "paos-data-migration-rollback/v1", "restored": str(path), "replayed": True}
    contact = Path(before["plan"]["contact_target"])
    if before.get("state") != "rollback_prepared":
        current = _read_json(contact) if contact.exists() else before["contact"]
        for source in before["plan"]["contact_sources"]:
            old = Path(source["path"])
            if not old.exists() or _sha(old) != source["sha256"]:
                raise ValueError(f"Old Contact changed after migration: {old}; preserve both stores")
        routes = before["plan"]["contact_routes"]
        owners = {}
        for source in before["plan"]["contact_sources"]:
            original = _read_json(Path(before["backup"]) / "contact" / source["scope"] / "native-targets.json")
            for key in original:
                owners.setdefault(key, []).append(source["scope"])
        split = {r["scope"]: {} for r in routes}
        for key, value in current.items():
            scopes = owners.get(key) or [r["scope"] for r in routes if key in r["homes"]
                or value.get("project_id") and str(value["project_id"]) == r["project_id"]]
            if not scopes:
                raise ValueError(f"New Contact has no registered rollback owner: {key}; Data preserved")
            for scope in scopes:
                split[scope][key] = value
        for item in [*before["mail"], *before["ui"]]:
            if Path(item["new"]).exists() and Path(item["old"]).exists():
                raise ValueError(f"Rollback old path exists: {item['old']}")
        # Preserve a complete cutover snapshot before restoring old-code routes.
        archive = Path(before["backup"]) / "rollback-current"
        _write_json(archive / "contact.json", current)
        for kind in ("mail", "ui"):
            for item in before[kind]:
                new = Path(item["new"])
                dest = archive / kind / item["scope"]
                if new.is_dir():
                    shutil.copytree(new, dest, dirs_exist_ok=True)
                elif new.is_file():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(new, dest)
        before["rollback_contact"] = split
        before["state"] = "rollback_prepared"
        _write_json(path, before)
    for route in before["plan"]["contact_routes"]:
        _write_json(Path(route["path"]), before["rollback_contact"][route["scope"]])
    for item in [*before["mail"], *before["ui"]]:
        new, old = Path(item["new"]), Path(item["old"])
        if new.exists():
            old.parent.mkdir(parents=True, exist_ok=True)
            if old.exists():
                raise ValueError(f"Rollback old path exists: {old}")
            shutil.move(str(new), str(old))
    if contact.exists():
        contact.unlink()
    before["state"] = "rolled_back"
    _write_json(path, before)
    return {"ok": True, "schema": "paos-data-migration-rollback/v1",
            "restored": str(path)}
