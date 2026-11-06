"""Check and explicitly distribute the marked common AGENTS section.

The canonical source is System/Project-Template/AGENTS.md. Registered project
vaults are the only destinations. Project-specific text is always preserved.
No project creation, registry modification, service calls or background jobs.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from dataclasses import dataclass

from paos_installation import effective_data_root, load_installation_descriptor
from paos_registry import ProjectRegistry
from paos_workstation import posix_windows_drive_locator

START = "<!-- paoe:common:start -->"
END = "<!-- paoe:common:end -->"
STAMP = "<!-- paoe:common:source-sha256: {} -->"
STAMP_RE = re.compile(r"^<!-- paoe:common:source-sha256: ([0-9a-f]{64}) -->\n")


class CommonError(ValueError):
    pass


@dataclass(frozen=True)
class CommonBlock:
    before: str
    body: str
    after: str
    stamp: str | None


def _normalized(text: str) -> str:
    return text.replace("\r\n", "\n")


def parse_block(text: str, *, require_stamp: bool) -> CommonBlock:
    """Split template-owned and project-owned bytes at explicit markers.

    The source has no stamp; installed copies carry the hash of the previous
    canonical body. A mismatch is an intentional human edit, not a stale
    version that the distributor may overwrite.
    """
    normalized = _normalized(text)
    if normalized.count(START) != 1 or normalized.count(END) != 1:
        raise CommonError("公共区标记缺失、重复或不完整")
    left = normalized.index(START)
    right = normalized.index(END)
    if left >= right or (left and normalized[left - 1] != "\n"):
        raise CommonError("公共区标记顺序或位置不合法")
    if not normalized.startswith("\n", left + len(START)):
        raise CommonError("公共区起始标记后需要换行")
    body_start = left + len(START) + 1
    raw_body = normalized[body_start:right]
    if not raw_body or not raw_body.endswith("\n"):
        raise CommonError("公共区正文不能为空，且必须以换行结尾")
    stamp = None
    if require_stamp:
        match = STAMP_RE.match(raw_body)
        if match is None:
            raise CommonError("生效 AGENTS 缺少公共区来源指纹；需人工首次纳管")
        stamp = match.group(1)
        raw_body = raw_body[match.end():]
        if not raw_body:
            raise CommonError("生效公共区没有正文")
    elif raw_body.startswith("<!-- paoe:common:source-sha256:"):
        raise CommonError("母本不应附带派生区指纹")
    return CommonBlock(normalized[:body_start], raw_body, normalized[right:], stamp)


def body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def managed_section(source: CommonBlock, *, newline: str = "\n") -> str:
    """Return the section contents between START and END, stamp included."""
    data = STAMP.format(body_hash(source.body)) + "\n" + source.body
    return data.replace("\n", newline)


def source_block(template: Path) -> CommonBlock:
    if template.is_symlink() or not template.is_file():
        raise CommonError(f"母本文件不可读或是符号链接：{template}")
    return parse_block(template.read_bytes().decode("utf-8"), require_stamp=False)


@dataclass(frozen=True)
class TargetStatus:
    project_id: str
    path: Path
    status: str  # in-sync / stale / conflict / unavailable
    reason: str
    before: bytes | None = None
    after: bytes | None = None


def inspect_target(project_id: str, path: Path, source: CommonBlock) -> TargetStatus:
    if path.is_symlink() or not path.is_file():
        return TargetStatus(project_id, path, "unavailable", "不存在、非普通文件或符号链接")
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        return TargetStatus(project_id, path, "unavailable", f"读取失败：{exc}")
    unsealed = False
    try:
        block = parse_block(text, require_stamp=True)
    except CommonError as exc:
        # A freshly copied template has correct markers/body but no source
        # fingerprint yet. It may be sealed without rewriting the body.
        if "缺少公共区来源指纹" not in str(exc):
            return TargetStatus(project_id, path, "conflict", str(exc))
        try:
            block = parse_block(text, require_stamp=False)
        except CommonError:
            return TargetStatus(project_id, path, "conflict", "公共区格式不正确，须人工审阅")
        unsealed = True
    previous = body_hash(block.body)
    current = body_hash(source.body)
    if unsealed:
        if previous != current:
            return TargetStatus(project_id, path, "conflict", "无指纹的公共区与母本不同，须人工合并")
    elif block.stamp != previous:
        return TargetStatus(project_id, path, "conflict", "派生公共区已被人工修改或指纹无效")
    elif previous == current:
        return TargetStatus(project_id, path, "in-sync", "公共区与母本一致")
    # Retain all material outside markers byte for byte, including original line ending.
    # Find offsets in the original string (not in its normalized copy).
    start = text.index(START) + len(START)
    end = text.index(END)
    # START marker ends at its line; replace only content between marker and END.
    end_of_start_line = text.find("\n", start)
    if end_of_start_line < 0 or end_of_start_line > end:
        return TargetStatus(project_id, path, "conflict", "公共区行结构非法")
    newline = "\r\n" if text[end_of_start_line - 1:end_of_start_line + 1] == "\r\n" else "\n"
    updated = text[:end_of_start_line + 1] + managed_section(source, newline=newline) + text[end:]
    reason = "新复制的公共区待附来源指纹" if unsealed else "派生区仍是原样旧版"
    return TargetStatus(project_id, path, "stale", reason, raw, updated.encode("utf-8"))


def registered_targets(installation_file: Path, selected: list[str]) -> list[tuple[str, Path]]:
    descriptor = load_installation_descriptor(installation_file)
    if not descriptor.get("configured"):
        raise CommonError(f"安装描述未配置：{installation_file}")
    directory = effective_data_root(descriptor) / "project-registry" / "projects"
    registry = ProjectRegistry(installation_file)
    records = sorted(directory.glob("*.json"))
    ids = {path.stem for path in records}
    if selected and not set(selected).issubset(ids):
        raise CommonError(f"请求的 Project 不在 Registry 中：{sorted(set(selected) - ids)}")
    result = []
    for path in records:
        if selected and path.stem not in selected:
            continue
        record = registry.read_record(path.stem)
        project_root = str(record.get("root_path") or "").strip()
        if not project_root:
            raise CommonError(f"Registry 未提供 Project 根：{path.stem}")
        root = Path(posix_windows_drive_locator(project_root)).expanduser()
        # The registered root, not a scan or candidate file, is authoritative.
        result.append((path.stem, root / "AGENTS.md"))
    return result


def _atomic_update(status: TargetStatus) -> None:
    if status.status != "stale" or status.before is None or status.after is None:
        raise CommonError(f"只允许写入 stale 项：{status.path}")
    path = status.path
    staged: Path | None = None
    try:
        if path.is_symlink() or not path.is_file():
            raise CommonError(f"目标已变化：{path}")
        mode = stat.S_IMODE(path.stat().st_mode)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".agents-common-",
                                         suffix=".tmp", delete=False) as handle:
            staged = Path(handle.name)
            handle.write(status.after)
        os.chmod(staged, mode)
        # This prevents ordinary intervening edits; does not claim a cross-file transaction.
        if path.is_symlink() or path.read_bytes() != status.before:
            raise CommonError(f"写入前原件已变化；不覆盖：{path}")
        os.replace(staged, path)
        staged = None
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    """Expose check/diff/apply; no schedule, loop or periodic reconciliation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True, help="System Project-Template/AGENTS.md")
    parser.add_argument("--installation-file", type=Path, help="当前安装描述；--print-block 不需要")
    parser.add_argument("--project", action="append", default=[], help="只检查/分发某个已登记项目，可重复")
    parser.add_argument("--all", action="store_true", help="分发所有登记项目；必须显式选择")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="只读校验，一致返回 0")
    mode.add_argument("--diff", action="store_true", help="只读显示可分发的差异")
    mode.add_argument("--apply", action="store_true", help="替换已校验的旧公共区")
    mode.add_argument("--print-block", action="store_true", help="打印一次人工纳管使用的带签名公共区")
    args = parser.parse_args(argv)
    try:
        source = source_block(args.template)
        if args.print_block:
            print(START)
            print(managed_section(source), end="")
            print(END)
            return 0
        if args.installation_file is None:
            raise CommonError("--check/--diff/--apply 必须提供 --installation-file")
        if args.all and args.project:
            raise CommonError("--all 与 --project 不可同时选择")
        if args.apply and not (args.project or args.all):
            raise CommonError("--apply 必须显式指定 --project 或 --all")
        targets = registered_targets(args.installation_file, args.project)
        statuses = [inspect_target(pid, p, source) for pid, p in targets]
        for item in statuses:
            print(f"{item.project_id}: {item.status} — {item.reason} ({item.path})")
            if args.diff and item.status == "stale":
                print("".join(difflib.unified_diff(
                    item.before.decode("utf-8").splitlines(keepends=True),
                    item.after.decode("utf-8").splitlines(keepends=True),
                    fromfile=f"{item.path}:old", tofile=f"{item.path}:new")), end="")
        # Conservative: do not partially apply when any selected target is unsafe.
        blocked = [item for item in statuses if item.status in ("conflict", "unavailable")]
        if blocked:
            print("存在不能自动分发的项目；先人工合并或修复，未写入。", file=sys.stderr)
            return 1
        if args.apply:
            for item in statuses:
                if item.status == "stale":
                    _atomic_update(item)
                    print(f"updated: {item.project_id} ({item.path})")
            return 0
        return 1 if any(item.status == "stale" for item in statuses) else 0
    except (CommonError, OSError, UnicodeError, ValueError, RuntimeError) as exc:
        print(f"AGENTS 公共区校验/分发失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
