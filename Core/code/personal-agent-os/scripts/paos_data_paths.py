"""Installation-scoped paths for machine-owned runtime data.

Business Mail/Notice, TODO/ENTRY and project documents stay in their existing
Home/Project locations. Only machine-owned Contact, dispatch and UI preferences
move under the installation Data root.
"""
from __future__ import annotations

import re
from pathlib import Path

from paos_installation import (
    effective_data_root, load_installation_descriptor, resolve_installation_path,
)

SCOPE_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def _descriptor(installation_path: str | Path | None = None) -> dict:
    return load_installation_descriptor(
        resolve_installation_path(str(installation_path) if installation_path else None))


def data_root(installation_path: str | Path | None = None) -> Path:
    return effective_data_root(_descriptor(installation_path))


def contact_store_path(installation_path: str | Path | None = None) -> Path:
    return data_root(installation_path) / "contact" / "native-targets.json"


def project_scope(project_id: str) -> str:
    value = str(project_id or "").strip()
    if not value:
        raise ValueError("project_id is required")
    scope = f"project-{value}"
    if not SCOPE_RE.fullmatch(scope):
        raise ValueError(f"invalid project scope: {scope}")
    return scope


def rooter_scope(home_id: str = "rooter-001") -> str:
    value = str(home_id or "rooter-001").strip()
    if value == "rooter-001":
        return "rooter"
    scope = f"rooter-{value}"
    if not SCOPE_RE.fullmatch(scope):
        raise ValueError(f"invalid rooter scope: {scope}")
    return scope


def scope_for_root(root: Path, installation_path: str | Path) -> str:
    """Resolve a legacy caller's sender root through the installation registry."""
    from paos_registry import ProjectRegistry
    from paos_workstation import posix_windows_drive_locator
    descriptor = _descriptor(installation_path)
    root = Path(root).resolve()
    matches = []
    if descriptor.get("rooter_home") and root == Path(posix_windows_drive_locator(descriptor["rooter_home"])).resolve():
        matches.append(rooter_scope())
    registry = ProjectRegistry(Path(installation_path))
    directory = effective_data_root(descriptor) / "project-registry/projects"
    for file in directory.glob('*.json'):
        record = registry.read_record(file.stem)
        if root == Path(posix_windows_drive_locator(record['root_path'])).resolve():
            matches.append(project_scope(record['id']))
    if len(matches) != 1:
        raise ValueError('Sender root must match exactly one registered scope')
    return matches[0]


def mail_dispatch_dir(scope: str,
                      installation_path: str | Path | None = None) -> Path:
    if not SCOPE_RE.fullmatch(str(scope or "")):
        raise ValueError("invalid mail scope")
    return data_root(installation_path) / "mail" / scope / "dispatch"


def ui_board_path(scope: str,
                  installation_path: str | Path | None = None) -> Path:
    if not SCOPE_RE.fullmatch(str(scope or "")):
        raise ValueError("invalid UI scope")
    return data_root(installation_path) / "ui" / scope / "board.json"
