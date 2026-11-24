"""Read phase inputs from the registered Home. This command has no writers.

Unresolved Current task references select no business Task. The exact Tasks
section remains available for Home maintenance; explicit task IDs must resolve.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import unquote

from paos_todo import TodoProblem, parse_todo
from paos_workstation import posix_windows_drive_locator


def _section(text, header):
    lines = text.splitlines(keepends=True)
    level = len(header) - len(header.lstrip("#"))
    start = next((i for i, line in enumerate(lines) if line.rstrip() == header), None)
    if start is None:
        return ""
    end = next(
        (i for i in range(start + 1, len(lines)) if re.match(r"^#{1," + str(level) + r"}\s", lines[i])),
        len(lines),
    )
    return "".join(lines[start:end]).rstrip()


def local_source(root, locator):
    """Resolve file locators without treating an HTTP reference as a local file."""
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", locator):
        return None
    raw = unquote(locator.split("#", 1)[0])
    return (root / posix_windows_drive_locator(raw)).resolve()


def read_context(home, *, staff_number, reason="resume", task_id="", sources=()):
    home_path = Path(home["home_path"])
    project = Path(home["project_root"]) if home["project_root"] else home_path
    rooter = home["home_kind"] == "rooter"
    documents, missing, references, omitted = [], [], [], []
    result = {
        "schema": "paoe-context/v1",
        "home_id": home["home_id"],
        "task_id": task_id,
        "reason": reason,
        "documents": documents,
        "missing": missing,
        "references": references,
        "omitted": omitted,
    }
    seen = set()

    def read(kind, path, *, transform=None, optional=False):
        path = Path(path)
        issues = omitted if optional else missing
        try:
            with path.open("r", encoding="utf-8-sig") as f:
                text = f.read()
                stat = os.fstat(f.fileno())
        except FileNotFoundError:
            issues.append({"kind": kind, "path": str(path), "reason": "missing"})
            return ""
        except (OSError, UnicodeError) as exc:
            issues.append({"kind": kind, "path": str(path), "reason": str(exc)})
            return ""
        body = transform(text) if transform else text
        if not body.strip():
            issues.append({"kind": kind, "path": str(path), "reason": "text_missing"})
        elif (kind, str(path)) not in seen:
            seen.add((kind, str(path)))
            documents.append(
                {
                    "kind": kind,
                    "path": str(path),
                    "body": body,
                    "version": f"{stat.st_mtime_ns}:{stat.st_size}",
                }
            )
        return text

    guide = read("guide", project / "AGENTS.md")
    if not rooter:
        read("home_rules", home_path / "AGENTS.md", optional=True)
        read("role", project / "TEAM.md", transform=lambda text: _section(text, "### " + staff_number))
        read("project", project / "INDEX.md")
    read("entry", home_path / "ENTRY.md")
    todo_path = home_path / "TODO.md"
    todo_text = read(
        "current",
        todo_path,
        transform=lambda t: "\n\n".join(
            part for part in (_section(t, "# Pinned"), _section(t, "# Current")) if part
        ),
    )
    related = []
    if todo_text:
        try:
            todo = parse_todo(todo_text)
        except TodoProblem as exc:
            missing.append({"kind": "current", "path": str(todo_path), "reason": exc.code})
        else:
            related = list(todo["current"].get("context_refs", []))
            if not task_id:
                anchors = [r[5:] for r in related if r.startswith("task:")]
                if len(anchors) == 1 and any(t["id"] == anchors[0] for t in todo["tasks"]):
                    task_id = anchors[0]
                    result["task_id"] = task_id
                elif anchors:
                    result["task_selection"] = {
                        "state": "unresolved",
                        "context_refs": ["task:" + anchor for anchor in anchors],
                    }
                    documents.append(
                        {
                            "kind": "task_recovery",
                            "path": str(todo_path),
                            "version": next(d["version"] for d in documents if d["kind"] == "current"),
                            "body": _section(todo_text, "# Tasks"),
                        }
                    )
            if task_id:
                task = next((t for t in todo["tasks"] if t["id"] == task_id), None)
                if not task:
                    missing.append({"kind": "task", "path": str(todo_path), "reason": "task_missing"})
                else:
                    rows = _section(todo_text, "# Tasks").splitlines(keepends=True)[1:]
                    start = next(
                        i
                        for i, row in enumerate(rows)
                        if re.match(r"^- \[[ /?x-]\] \*\*" + re.escape(task_id) + r"\*\* · ", row)
                    )
                    end = next(
                        (i for i in range(start + 1, len(rows)) if rows[i].startswith("- [")), len(rows)
                    )
                    documents.append(
                        {
                            "kind": "task",
                            "path": str(todo_path),
                            "version": next(d["version"] for d in documents if d["kind"] == "current"),
                            "body": "".join(rows[start:end]).strip(),
                        }
                    )
                    related += task["source_refs"]
                    if any(ref.startswith("team-plan:") for ref in task["source_refs"]):
                        read("work_lead", project / "WORK-LEAD.md")
    background = re.search(r"\[共同背景\]\((?:<([^>]+)>|([^)]+))\)", guide)
    if background:
        locator = background.group(1) or background.group(2)
        path = local_source(project, locator)
        if path is None:
            missing.append({"kind": "background", "path": locator, "reason": "local_source_required"})
        else:
            read("background", path)
    else:
        missing.append(
            {
                "kind": "background",
                "path": str(project / "AGENTS.md"),
                "reason": "background_locator_missing",
            }
        )

    # Explicit inputs are required. Other external links remain references.
    for locator in dict.fromkeys([*sources, *related]):
        if locator.startswith("mail:"):
            mid = locator.removeprefix("mail:").removesuffix(".md")
            path = (
                home_path / "mailbox" / (mid + ".md") if re.fullmatch(r"[A-Za-z0-9._-]+", mid) else None
            )
        elif re.match(r"^[a-z]+(?:-[a-z]+)*:", locator, re.I) and not re.match(
            r"^[a-z]:[/\\]", locator, re.I
        ):
            path = None
        else:
            path = local_source(project, locator)
        if path is None:
            references.append(locator)
            (missing if locator in sources else omitted).append(
                {"kind": "input", "path": locator, "reason": "requires_original_reader"}
            )
            continue
        if path.suffix.lower() not in {".md", ".txt"} or path.is_dir():
            references.append(locator)
            (missing if locator in sources else omitted).append(
                {"kind": "input", "path": locator, "reason": "text_original_required"}
            )
            continue
        read("input", path, optional=locator not in sources)
    result["ok"] = not missing
    return result
