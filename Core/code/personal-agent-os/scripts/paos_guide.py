"""Read-only Markdown Guide comparison exposed by ``paos workstation guide-diff``.

The retired Work/Session/Cycle guide promotion mechanism was removed.
This module owns no Guide files: callers supply two existing paths, and the
return value carries both fingerprints so a reviewer can check later edits.
"""
from __future__ import annotations

import difflib
import hashlib
from pathlib import Path
from typing import Any


class GuideProblem(Exception):
    """A Guide review/promotion failure with a stable CLI-facing code."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_required(path: Path, *, code: str, label: str) -> bytes:
    try:
        if not path.is_file():
            raise FileNotFoundError(path)
        return path.read_bytes()
    except OSError as exc:
        raise GuideProblem(
            code,
            f"{label} 不可读取：{path}",
            {"path": str(path), "os_error": str(exc)},
        ) from exc


def _decode_guide(data: bytes, *, path: Path) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GuideProblem(
            "guide_not_utf8",
            f"Guide 必须是 UTF-8 Markdown：{path}",
            {"path": str(path)},
        ) from exc


def build_guide_diff(
    candidate_src: Path,
    *,
    canonical_src: Path,
) -> dict[str, Any]:
    """Compare existing Markdown files without changing either source.

    Learning note: input bytes and SHA-256 make the review reproducible.
    Workless：无 Work/Cycle 定位；两者都是真实文件路径。"""
    candidate_path = Path(candidate_src)
    canonical_path = Path(canonical_src)
    candidate = _read_required(candidate_path, code="guide_candidate_missing", label="Guide candidate")
    canonical = _read_required(canonical_path, code="canonical_guide_missing", label="Canonical Guide")
    candidate_text = _decode_guide(candidate, path=candidate_path)
    canonical_text = _decode_guide(canonical, path=canonical_path)
    diff = chr(10).join(
        difflib.unified_diff(
            canonical_text.splitlines(),
            candidate_text.splitlines(),
            fromfile=str(canonical_path),
            tofile=str(candidate_path),
            lineterm="",
        )
    )
    candidate_sha = _sha256(candidate)
    canonical_sha = _sha256(canonical)
    return {
        "schema": "paos-guide-diff/v2",
        "candidate_path": str(candidate_path),
        "canonical_path": str(canonical_path),
        "changed": candidate_sha != canonical_sha,
        "candidate_sha256": candidate_sha,
        "canonical_sha256": canonical_sha,
        "diff": diff,
    }
