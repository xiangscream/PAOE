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
        if old.is_dir():
            sources.append((project_scope(record["id"]), old,
                            mail_dispatch_dir(project_scope(record["id"]), installation)))
    rooter = _rooter_home(installation)
    if rooter:
        old = rooter / ".paos" / "mail" / "dispatch"
        if old.is_dir():
            sources.append((rooter_scope(), old,
                            mail_dispatch_dir(rooter_scope(), installation)))
    return sources


def _ui_sources(installation: Path) -> list[tuple[str, Path, Path]]:
    sources = []
    for record in _project_records(installation):
        root = Path(record["root_path"])
        old = root / ".paos" / "ui" / "board.json"
        if old.is_file():
            sources.append((project_scope(record["id"]), old,
                            ui_board_path(project_scope(record["id"]), installation)))
    rooter = _rooter_home(installation)
    if rooter:
        old = rooter / ".paos" / "ui" / "board.json"
        if old.is_file():
            sources.append((rooter_scope(), old,
                            ui_board_path(rooter_scope(), installation)))
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
                   "sha256": _sha(old)})
    return {
        "ok": True,
        "schema": "paos-data-migration-plan/v1",
        "installation": str(installation),
        "data_root": str(data_root(installation)),
        "contact_target": str(contact_store_path(installation)),
        "contact_sources": contact_sources,
        "contact_keys": sorted(contacts),
        "mail": mail,
        "ui": ui,
        "execute_hint": "rerun with execute and before_state",
    }


def execute(installation_path: str | Path, before_state: str | Path) -> dict[str, Any]:
    installation = resolve_installation_path(str(installation_path))
    value = plan(installation)
    before_path = Path(before_state).expanduser().resolve()
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
        shutil.copytree(old, target)
        mail_backups.append({"scope": item["scope"], "old": item["old"],
                             "new": item["new"], "backup": str(target)})
    ui_backups = []
    for item in value["ui"]:
        old = Path(item["old"])
        target = backup / "ui" / item["scope"] / "board.json"
        target.parent.mkdir(parents=True, exist_ok=True)
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
    }
    before_path.parent.mkdir(parents=True, exist_ok=True)
    before_path.write_text(json.dumps(before, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    contact_target = Path(value["contact_target"])
    contact_target.parent.mkdir(parents=True, exist_ok=True)
    stage = contact_target.with_name(f".{contact_target.name}.staging")
    stage.write_text(json.dumps(contacts, ensure_ascii=False, indent=2,
                                sort_keys=True) + "\n", encoding="utf-8")
    os.replace(stage, contact_target)
    for item in value["mail"]:
        old, new = Path(item["old"]), Path(item["new"])
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old), str(new))
    for item in value["ui"]:
        old, new = Path(item["old"]), Path(item["new"])
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old), str(new))
    return {"ok": True, "schema": "paos-data-migration-result/v1",
            "before_state": str(before_path), "backup": str(backup),
            "contact_target": str(contact_target),
            "mail_moved": len(value["mail"]), "ui_moved": len(value["ui"])}


def rollback(before_state: str | Path) -> dict[str, Any]:
    path = Path(before_state).expanduser().resolve()
    before = _read_json(path)
    for item in before.get("mail", []):
        new, old = Path(item["new"]), Path(item["old"])
        if new.exists():
            old.parent.mkdir(parents=True, exist_ok=True)
            if old.exists():
                raise ValueError(f"Rollback old path exists: {old}")
            shutil.move(str(new), str(old))
    for item in before.get("ui", []):
        new, old = Path(item["new"]), Path(item["old"])
        if new.exists():
            old.parent.mkdir(parents=True, exist_ok=True)
            if old.exists():
                raise ValueError(f"Rollback old path exists: {old}")
            shutil.move(str(new), str(old))
    contact = Path(before["plan"]["contact_target"])
    if contact.exists():
        contact.unlink()
    return {"ok": True, "schema": "paos-data-migration-rollback/v1",
            "restored": str(path)}
