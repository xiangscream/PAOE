"""Find project, method and experience originals through the installed QMD and Library."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from paos_installation import effective_data_root, resolve_library_roots_path
from paos_library import LibraryProblem, load_library_roots, parse_frontmatter, search_library_resources
from paos_registry import ProjectRegistry
from paos_workstation import posix_windows_drive_locator


def add_search_parser(group):
    command = group.add_parser("search", help="Find originals across the project, methods and experience")
    command.add_argument("home", help="Registered Home; its own project is selected by default")
    command.add_argument("query")
    command.add_argument("--scope", choices=["project", "methods", "experience"], action="append")
    command.add_argument("--project", help="Select another registered project")
    command.add_argument("--mode", choices=["hybrid", "lexical", "semantic"], default="hybrid")
    command.add_argument("--limit", type=int, default=8)
    plan = group.add_parser("collections", help="Show QMD collection roots and registration commands")
    plan.add_argument("home")
    plan.add_argument("--project", help="Select another registered project")


class QmdUnavailable(ValueError):
    pass


def _project_collection(home, installation, project_id):
    project_id = project_id or home["project_id"]
    if not project_id:
        raise ValueError("安装级工位检索项目时需用 --project 指定登记项目")
    root = ProjectRegistry(installation).read_record(project_id)["root_path"]
    return ("project", "project-" + project_id, root, "INDEX.md,{Topics,Works,Decisions,Materials}/**/*.md")


def _method_collections(roots):
    yield ("methods", "library-workflow", roots["workflow_root"], "{Guides,Workflows,Templates}/**/*.md")
    yield ("methods", "library-skill", roots["skill_root"], "*/SKILL.md,*/references/**/*.md")
    if roots.get("tool_catalog"):
        catalog = Path(posix_windows_drive_locator(str(roots["tool_catalog"])))
        yield ("methods", "library-tools", str(catalog), catalog.name)


def collection_plan(home, installation, descriptor, project):
    roots = load_library_roots(resolve_library_roots_path(installation=descriptor))
    if not roots.get("registered"):
        raise LibraryProblem("library_roots_not_registered", "此安装尚未登记方法库", {})
    targets = [_project_collection(home, installation, project), *_method_collections(roots)]
    rows = []
    for scope, name, expected, mask in targets:
        root = Path(posix_windows_drive_locator(str(expected)))
        folder = root.parent if name == "library-tools" else root
        rows.append({"scope": scope, "collection": name, "root": str(folder), "mask": mask,
                     "inspect": ["collection", "show", name],
                     "add_if_missing": ["collection", "add", str(folder), "--name", name, "--mask", mask]})
    rows.append({"scope": "experience", "collection": "exm", "inspect": ["collection", "show", "exm"]})
    return {"ok": True, "launcher": str(effective_data_root(descriptor) / "exm" / "exm.ps1"),
            "collections": rows, "refresh": [["update"], ["embed"]], "writes": []}


def _run_qmd(launcher, arguments):
    if not launcher.is_file():
        raise QmdUnavailable(f"登记安装缺少 QMD 入口：{launcher}")
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise QmdUnavailable("当前安装没有运行 QMD 入口所需的 PowerShell")
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-File", str(launcher), *arguments],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if result.returncode:
        raise QmdUnavailable((result.stderr or result.stdout).strip() or f"QMD 退出码 {result.returncode}")
    return result.stdout.lstrip("\ufeff")


def qmd_collection_root(launcher, name):
    info = _run_qmd(launcher, ["collection", "show", name])
    for line in info.splitlines():
        key, sep, value = line.strip().partition(":")
        if key == "Path" and sep and Path(value.strip()).is_absolute():
            return Path(value.strip()).resolve()
    raise QmdUnavailable(f"QMD 未给出集合 {name} 的绝对根目录")


def query_qmd(launcher, collection, query, mode, limit):
    # QMD's typed clauses also keep leading dashes in a search term from becoming CLI options.
    lanes = {"lexical": ("lex",), "semantic": ("vec",), "hybrid": ("lex", "vec")}
    expression = "\n".join(f"{lane}: {query}" for lane in lanes[mode])
    raw = _run_qmd(launcher, ["query", expression, "--no-rerank", "-c", collection,
                              "-n", str(limit), "--format", "json", "--full-path"])
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as error:
        raise QmdUnavailable("QMD 未返回可读的 JSON 结果") from error
    if not isinstance(rows, list):
        raise QmdUnavailable("QMD 检索结果不是列表")
    if any(not isinstance(row, dict) or not isinstance(row.get("file"), str) for row in rows):
        raise QmdUnavailable("QMD 检索结果缺少原件位置")
    return rows


def _original(locator, expected):
    """QMD emits the original absolute path, or a qmd:// locator for a moved file."""
    if locator.startswith("qmd://"):
        return {}, "index_only"
    path = Path(locator)
    if not path.is_absolute():
        raise QmdUnavailable(f"索引没有返回绝对原件位置：{locator}")
    path = path.resolve()
    if expected is None:
        raise QmdUnavailable("无法核对该集合的原件根目录")
    root = Path(posix_windows_drive_locator(str(expected))).resolve()
    if not (path == root or (root.is_dir() and path.is_relative_to(root))):
        raise QmdUnavailable(f"集合原件在当前安装登记范围之外：{path}")
    try:
        with path.open(encoding="utf-8-sig") as stream:
            first = stream.readline()
            front = [first]
            if first.strip() == "---":
                for line in stream:
                    front.append(line)
                    if line.strip() == "---":
                        break
        return parse_frontmatter("".join(front)), "local"
    except FileNotFoundError:
        return {}, "index_only"


def _qmd_hit(row, scope, collection, expected):
    locator = row["file"]
    if locator.startswith("qmd://") and not locator.startswith("qmd://" + collection + "/"):
        raise QmdUnavailable(f"索引返回了其他集合的原件：{locator}")
    metadata, availability = _original(locator, expected)
    status = metadata.get("status")
    if not status and availability == "local":
        root = Path(posix_windows_drive_locator(str(expected))).resolve()
        relative = Path(locator).resolve().relative_to(root)
        if relative.parts and relative.parts[0].casefold() == "archive":
            status = "historical"
    return {
        "scope": scope, "title": row.get("title") or Path(locator).name,
        "description": metadata.get("description") or "",
        "collection_context": row.get("context") or "",
        "locator": locator, "availability": availability,
        "date": metadata.get("date") or metadata.get("updated_at") or metadata.get("created_at") or None,
        "status": status,
        "sections": [{"line": row.get("line"), "snippet": row.get("snippet", "")}],
        "sources": [collection],
    }


def search_context(args, home, installation, descriptor):
    query = args.query.strip()
    if not query or "\n" in query or "\r" in query or not 1 <= args.limit <= 30:
        raise ValueError("检索需要一行实际问题，limit 为 1–30")
    scopes = list(dict.fromkeys(args.scope or ["project", "methods", "experience"]))
    launcher = effective_data_root(descriptor) / "exm" / "exm.ps1"
    collections = []
    ranked = []
    coverage = []
    if "project" in scopes:
        collections.append(_project_collection(home, installation, args.project))
    if "methods" in scopes:
        try:
            roots = load_library_roots(resolve_library_roots_path(installation=descriptor))
            if not roots.get("registered"):
                raise LibraryProblem("library_roots_not_registered", "此安装尚未登记方法库", {})
            if args.mode != "semantic":
                library = search_library_resources(roots, query, limit=args.limit)
        except LibraryProblem as error:
            coverage.append({"source": "method-catalog", "state": "unavailable", "reason": str(error)})
        else:
            if args.mode != "semantic":
                ranked.append([
                    {
                        "scope": "methods", "title": hit["title"], "description": hit["description"],
                        "locator": hit["source_path"], "availability": "local", "date": None,
                        "status": hit["status"], "sections": [{"heading": h} for h in hit["matching_sections"]],
                        "sources": ["method-catalog"],
                    }
                    for hit in library["items"]
                ])
                coverage.append({"source": "method-catalog", "state": "searched"})
            collections.extend(_method_collections(roots))
    if "experience" in scopes:
        # The installation's existing QMD exm collection owns its filesystem locator.
        collections.append(("experience", "exm", None, None))
    for scope, name, root, _mask in collections:
        try:
            rows = query_qmd(launcher, name, query, args.mode, args.limit)
            if root is None and any(not row["file"].startswith("qmd://") for row in rows):
                root = qmd_collection_root(launcher, name)
            hits = [_qmd_hit(row, scope, name, root) for row in rows]
        except QmdUnavailable as error:
            coverage.append({"source": name, "scope": scope, "state": "unavailable", "reason": str(error)})
        else:
            ranked.append(hits)
            coverage.append({"source": name, "scope": scope, "state": "searched", "count": len(hits)})

    # Collection and catalog scores have different scales. Fuse ranks, once per file per source.
    originals, scores = {}, {}
    for hits in ranked:
        seen = set()
        for rank, hit in enumerate(hits, 1):
            key = Path(hit["locator"]).resolve() if hit["availability"] == "local" else hit["locator"]
            item = originals.setdefault(key, hit)
            if item is not hit:
                for field in ("sources", "sections"):
                    item[field].extend(value for value in hit[field] if value not in item[field])
                if not item["date"]:
                    item["date"] = hit["date"]
                if not item["description"]:
                    item["description"] = hit["description"]
            if key not in seen:
                scores[key] = scores.get(key, 0) + 1 / (60 + rank)
                seen.add(key)
    complete = all(entry["state"] == "searched" for entry in coverage)
    return {
        "ok": complete, "schema": "paoe-context-search/v1", "query": query, "mode": args.mode,
        "coverage": coverage, "results": [originals[k] for k in sorted(scores, key=scores.get, reverse=True)[:args.limit]],
    }
