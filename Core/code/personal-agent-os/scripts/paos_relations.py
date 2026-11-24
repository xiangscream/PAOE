"""Read explicit related-experience lists; derive backlinks without a second graph store."""

from collections import deque
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from paos_content import scoped_file
from paos_context import local_source


# The content owner uses named inline links. Angle-bracket destinations allow spaces/parentheses.
LINK = re.compile(r"\[([^\]\n]+)\]\((<[^>\n]+>|[^)\n]+)\)")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
RELATION_HEADINGS = {"相关经历", "相关主题"}


def _locator(path, raw):
    raw = raw.strip().strip("<>")
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", raw):
        return raw
    fragment = urlsplit(raw).fragment
    target = local_source(path.parent, raw)
    return str(target) + ("#" + unquote(fragment) if fragment else "")


def read_relations(path):
    edges, missing, level, fence = [], [], 0, ""
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            fence = "" if fence == marker else (fence or marker)
            continue
        if fence:
            continue
        heading = HEADING.match(line)
        if heading:
            if heading[2] in RELATION_HEADINGS:
                level = len(heading[1])
            elif level and len(heading[1]) <= level:
                level = 0
            continue
        if not level or not stripped.startswith("- "):
            continue
        text = stripped[2:]
        target = LINK.match(text)
        if target is None or not text[target.end():].strip(" —:：-"):
            missing.append({"source": str(path), "line": line_number,
                            "reason": "关系项须以命名链接开头，并保留关系理由和来源说明"})
            continue
        edges.append({"source": str(path), "target": _locator(path, target[2]),
                      "label": target[1], "explanation": text[target.end():].lstrip(" —:：-"),
                      "sources": [{"label": m[1], "locator": _locator(path, m[2])}
                                  for m in LINK.finditer(text[target.end():])],
                      "line": line_number})
    return edges, missing


def related(root, source, *, source_roots=(), depth=1, limit=8):
    if not 0 <= depth <= 3 or not 1 <= limit <= 30:
        raise ValueError("展开深度为0至3，节点预算为1至30")
    root = Path(root).resolve()
    start = scoped_file(root, source, source_roots=source_roots)
    candidates = {start}
    for folder in ("Topics", "Projects", "心得"):
        candidates.update((root / folder).rglob("*.md"))
    edges, missing = [], []
    for path in sorted(candidates):
        parsed, issues = read_relations(path)
        edges.extend(parsed)
        missing.extend(issues)

    def node(locator):
        return locator.split("#", 1)[0]

    adjacency = {}
    for edge in edges:
        for locator in (edge["source"], node(edge["target"])):
            adjacency.setdefault(locator, []).append(edge)
    visited, queue, truncated = {str(start): 0}, deque([str(start)]), False
    while queue:
        current = queue.popleft()
        if visited[current] == depth:
            continue
        for edge in adjacency.get(current, []):
            other = node(edge["target"]) if edge["source"] == current else edge["source"]
            if other in visited:
                continue
            if len(visited) == limit:
                truncated = True
                continue
            visited[other] = visited[current] + 1
            queue.append(other)
    selected = [e for e in edges if e["source"] in visited and node(e["target"]) in visited]
    return {"ok": True, "source": str(start), "depth": depth, "limit": limit,
            "nodes": [{"locator": key, "distance": distance} for key, distance in visited.items()],
            "relations": selected, "missing": [item for item in missing if item["source"] in visited],
            "truncated": truncated,
            "writes": []}
