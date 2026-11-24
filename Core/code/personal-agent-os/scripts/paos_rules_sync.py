"""Reconcile System's two managed rule documents inside the content observer."""

from pathlib import Path

from paos_agents_common import (CommonError, TargetStatus, inspect_document, project_roots, source_block,
                                update_target)
from paos_installation import effective_data_root, load_installation_descriptor
from paos_workstation import posix_windows_drive_locator


DOCUMENTS = ("AGENTS.md", "WORK-LEAD.md")
_DOCUMENT_NAMES = {name.casefold() for name in DOCUMENTS}


class RulesSync:
    def __init__(self, installation):
        self.installation = installation
        self.descriptor = load_installation_descriptor(installation)
        self.data = effective_data_root(self.descriptor).resolve()
        self.registry = self.data / "project-registry" / "projects"
        source = Path(posix_windows_drive_locator(self.descriptor["source_root"])).expanduser()
        self.source = source
        self.templates = None
        if tuple(part.casefold() for part in source.parts[-3:]) == ("core", "code", "personal-agent-os"):
            self.templates = source.parents[2].resolve() / "Project-Template"
        rooter = self.descriptor.get("rooter_home")
        self.rooter = Path(posix_windows_drive_locator(rooter)).expanduser().resolve() if rooter else None
        self.targets, self.errors = {}, []

    def refresh(self):
        roots, self.errors = project_roots(self.installation, self.descriptor)
        if not any(item.project_id == "registry" for item in self.errors):
            try:
                if not self.registry.is_dir():
                    self.errors.append(TargetStatus("registry", self.registry, "unavailable", "项目登记目录不可读"))
            except OSError as exc:
                self.errors.append(TargetStatus("registry", self.registry, "unavailable", str(exc), retry=True))
        self.targets = {}
        for project, root in roots.items():
            if root.is_relative_to(self.data) or (self.rooter is not None and root.is_relative_to(self.rooter)):
                self.errors.append(TargetStatus(project, root, "unavailable", "项目根落在运行数据或 Rooter 中"))
            else:
                self.targets[project] = root
        if self.rooter is not None:
            self.targets["rooter"] = self.rooter
        if self.templates is not None:
            source_directory = self.templates.resolve()
            for project, root in list(self.targets.items()):
                if root.is_relative_to(source_directory):
                    self.errors.append(TargetStatus(project, root, "unavailable", "母本目录不能作为分发目标"))
                    del self.targets[project]

    def directories(self):
        directories = {*self.targets.values(), self.registry}
        if self.templates is not None:
            directories.add(self.templates)
        return directories

    def accepts(self, path):
        if path.parent == self.registry:
            return path.suffix.lower() == ".json"
        return path.name.casefold() in _DOCUMENT_NAMES and path.parent in self.directories()

    def reconcile(self, *, apply=False):
        results = [_result(item) for item in self.errors]
        retry = any(item.retry for item in self.errors)
        if self.templates is None:
            results.append(_result(TargetStatus("system", self.source, "source_error",
                                                "安装的 source_root 未指向 System/Core/code/personal-agent-os")))
        else:
            for document in DOCUMENTS:
                template = self.templates / document
                try:
                    source = source_block(template)
                except (CommonError, UnicodeError, OSError) as exc:
                    results.append(_result(TargetStatus("system", template, "source_error", str(exc)), document))
                    retry |= isinstance(exc, OSError)
                    continue
                for target, root in self.targets.items():
                    path = root / document
                    try:
                        item = inspect_document(target, path, source)
                    except OSError as exc:
                        item = TargetStatus(target, path, "unavailable", f"读取失败：{exc}", retry=True)
                    retry |= item.retry
                    if apply and item.status == "stale":
                        try:
                            update_target(item, source)
                        except (OSError, CommonError) as exc:
                            item = TargetStatus(target, path, "write_failed", str(exc))
                            retry = True
                        else:
                            item = TargetStatus(target, path, "updated", "公共区与母本一致")
                    results.append(_result(item, document))
        ok = all(row["status"] in {"in-sync", "updated"} for row in results)
        return {"ok": ok, "event": "rules_sync", "targets": results}, retry


def _result(item, document=None):
    return {"target": item.project_id, "document": document, "path": str(item.path),
            "status": item.status, "reason": item.reason}
