"""Save explicitly selected native originals and their EXM read position."""

from __future__ import annotations

import argparse
from contextlib import closing
from itertools import islice
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from zipfile import BadZipFile

from paos_content import pack
from paos_exm_originals import BatchError, Origin, Source, dsh_export_lines, read_originals
from paos_installation import (
    InstallationProblem, effective_data_root, load_installation_descriptor, resolve_installation_path,
)
from paos_registry import ProjectRegistry, RegistryProblem
from paos_workstation import posix_windows_drive_locator


_EXM_PROJECT = "3005"
_FORMATS = {
    "codex-rollout": "codex",
    "opencode-v2": "opencode",
    "dsh-export": "dsh",
    "antigravity-transcript": "antigravity",
}
_COMMENT = "<!-- paoe-exm-originals "
_COMMENT_END = " -->"
_FENCE = re.compile(r"^ {0,3}([~]{3,}|[`]{3,})(.*)$")
_FINGERPRINT = re.compile(r"[0-9a-f]{64}")


def _path(locator):
    return Path(posix_windows_drive_locator(str(locator))).expanduser()


def _page_path(root, locator):
    selected = (root / _path(locator)).resolve()
    if selected.suffix.lower() != ".md" or not selected.is_relative_to(root):
        raise BatchError("select a Markdown source page within registered EXM")
    if selected.exists():
        if not selected.is_file():
            raise BatchError("selected EXM source page is not a file")
    elif not selected.is_relative_to((root / "Sessions").resolve()):
        raise BatchError("create new EXM source pages within Sessions")
    return selected


def _origins(path):
    if path is None:
        return {}
    records = json.loads(_path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(records, dict):
        raise BatchError("origins must map native IDs to kind and evidence_ref")
    for value in records.values():
        if (not isinstance(value, dict) or set(value) != {"kind", "evidence_ref"}
                or value["kind"] not in ("human", "system", "injected", "automation", "forwarded")
                or not isinstance(value["evidence_ref"], str) or not value["evidence_ref"].strip()):
            raise BatchError("invalid origin entry")
    return {message_id: Origin(**value) for message_id, value in records.items()}


def _slice_lines(stream, start, end):
    count = 0
    for count, line in enumerate(islice(stream, start - 1, end), 1):
        yield line
    if (end is not None and count != end - start + 1) or (count == 0 and start != 1):
        raise BatchError("selected line range extends past the supplied file")


def _read(source, path, previous, format, origins, start, end, message):
    scoped_lines = format in {"codex-rollout", "antigravity-transcript"}
    if start < 1 or (end is not None and end < start):
        raise BatchError("invalid selected line range")
    if not scoped_lines and (start != 1 or end is not None):
        raise BatchError("line ranges apply to Codex and Antigravity JSONL")
    options = {"format": format, "origins": origins, "selected_message_id": message}
    if format == "opencode-v2":
        return read_originals(source, json.loads(path.read_bytes()), previous, **options)
    if format == "dsh-export" and path.suffix.lower() == ".zip":
        with closing(dsh_export_lines(path)) as lines:
            return read_originals(source, lines, previous, **options)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        lines = _slice_lines(stream, start, end) if scoped_lines else stream
        return read_originals(source, lines, previous, start_line=start, **options)


def _existing_page(path):
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _read_marks(current, namespace):
    """Read published revision identities, skipping literal Markdown code blocks."""
    entries = {}
    binding = False
    fence = None
    for line in current.decode("utf-8-sig").splitlines() if current is not None else ():
        match = _FENCE.fullmatch(line)
        if fence is not None:
            if (match and match[1][0] == fence[0] and len(match[1]) >= len(fence)
                    and not match[2].strip()):
                fence = None
            continue
        if match:
            fence = match[1]
            continue
        if not line.startswith(_COMMENT):
            continue
        if not line.endswith(_COMMENT_END):
            raise BatchError("invalid EXM originals marker")
        mark = json.loads(line[len(_COMMENT):-len(_COMMENT_END)])
        if not isinstance(mark, dict):
            raise BatchError("invalid EXM originals marker")
        if set(mark) == {"namespace"}:
            if binding or mark["namespace"] != namespace:
                raise BatchError("this source page belongs to another originals stream")
            binding = True
            continue
        if not binding or set(mark) != {"id", "revision", "fingerprint"}:
            raise BatchError("invalid revision marker on the EXM source page")
        message_id, revision, fingerprint = mark["id"], mark["revision"], mark["fingerprint"]
        if (not isinstance(message_id, str) or type(revision) is not int
                or not isinstance(fingerprint, str) or not _FINGERPRINT.fullmatch(fingerprint)):
            raise BatchError("invalid revision marker on the EXM source page")
        history = entries.setdefault(message_id, [])
        if revision != len(history) + 1:
            raise BatchError("EXM source page has a missing or duplicate revision marker")
        history.append(fingerprint)
    if fence is not None:
        raise BatchError("close the open code block in the selected EXM source page before importing")
    return binding, entries


def _recover_previous(previous, namespace, entries):
    committed = previous["messages"] if previous is not None else {}
    for message_id, item in committed.items():
        history = entries.get(message_id, [])
        revision = item["revision"]
        if not 1 <= revision <= len(history) or history[revision - 1] != item["fingerprint"]:
            raise BatchError("published originals are missing or changed; restore their source-page markers")
    recovered = {message_id: {"revision": len(history), "fingerprint": history[-1]}
                 for message_id, history in entries.items()}
    count = sum(len(history) - committed.get(message_id, {}).get("revision", 0)
                for message_id, history in entries.items())
    if not count:
        return previous, 0
    base = previous or {"version": 1, "namespace": namespace}
    return {**base, "messages": recovered}, count


def _mark(value):
    # Double hyphens inside JSON strings must not acquire HTML comment semantics.
    return _COMMENT + pack(value).replace("--", "\\u002d\\u002d") + _COMMENT_END


def _block(text, language):
    fence = "`" * max(3, max((len(run) + 1 for run in re.findall(r"`+", text)), default=0))
    return f"{fence}{language}\n{text}\n{fence}\n"


def _append_bytes(current, binding, namespace, originals, proposed, count):
    chunks = []
    if current:
        chunks.append("\n\n")
    if not binding:
        chunks.extend((_mark({"namespace": namespace}), "\n\n## 会话原话\n\n"))
    for number, original in enumerate(originals, count + 1):
        message_id = original["message_id"]
        revision = original["revision"]
        marker = {"id": message_id, **proposed["messages"][message_id]}
        provenance = {key: value for key, value in original.items() if key != "text_parts"}
        chunks.append(f"### 原话 {number} · 修订 {revision}\n\n{_mark(marker)}\n\n")
        chunks.extend(_block(part, "text") + "\n" for part in original["text_parts"])
        chunks.append("来源与附件位置\n\n")
        chunks.append(_block(json.dumps(provenance, ensure_ascii=False, indent=2), "json") + "\n")
    return (current or b"") + "".join(chunks).encode("utf-8")


def _write_page(path, current, replacement):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".exm-originals-")
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(replacement)
            stream.flush()
            os.fsync(stream.fileno())
        if current is None:
            try:
                os.link(temporary, path)
            except FileExistsError as exc:
                raise BatchError("EXM source page appeared during the import; run again") from exc
        else:
            if _existing_page(path) != current:
                raise BatchError("EXM source page changed during the import; run again")
            os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _save_cursor(db, stream, page_key, cursor):
    db.execute("""INSERT INTO originals(stream, page, cursor) VALUES(?,?,?)
                  ON CONFLICT(stream) DO UPDATE SET cursor=excluded.cursor""",
               (stream, page_key, pack(cursor)))


def _position_without_rewind(previous, proposed):
    old = (previous or {}).get("position", {})
    new = proposed["position"]
    if old.get("source_ref") == new["source_ref"] and old.get("format") == new["format"]:
        for field in ("line", "seq"):
            if field in new and old.get(field) is not None:
                if new[field] is None or new[field] < old[field]:
                    return {**proposed, "position": old}
    return proposed


def publish_originals(installation, *, format, session_id, project_id, input_file, page,
                      origins_file=None, work_group=None, counterpart=None, start_line=1,
                      end_line=None, selected_message_id=None):
    """Append verified source revisions, then commit the consumption cursor."""
    if format not in _FORMATS or not session_id or not session_id.strip():
        raise BatchError("an exact native session and supported format are required")
    registry = ProjectRegistry(installation)
    if project_id != _EXM_PROJECT:
        registry.read_record(project_id)
    root = _path(registry.read_record(_EXM_PROJECT)["root_path"]).resolve(strict=True)
    target = _page_path(root, page)
    path = _path(input_file).resolve(strict=True)
    if not path.is_file() or path == target:
        raise BatchError("select a native input file distinct from the EXM source page")
    origins = _origins(origins_file)
    data = effective_data_root(load_installation_descriptor(installation))
    db_path = data / "exm" / "originals.sqlite3"
    source = Source(_FORMATS[format], session_id, project_id, str(path), work_group, counterpart)
    namespace = source.namespace()
    stream = pack(namespace)
    page_key = os.path.normcase(target.relative_to(root).as_posix())
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path, timeout=5)) as db, db:
        # Serialize importers. After a process interruption the source page may
        # be ahead of SQLite, so recover the published revisions before reading.
        db.execute("BEGIN IMMEDIATE")
        db.execute("""CREATE TABLE IF NOT EXISTS originals (
            stream TEXT PRIMARY KEY, page TEXT NOT NULL UNIQUE, cursor TEXT NOT NULL
        )""")
        row = db.execute("SELECT stream, page, cursor FROM originals WHERE stream=? OR page=?",
                         (stream, page_key)).fetchone()
        if row is not None and row[:2] != (stream, page_key):
            raise BatchError("keep the registered EXM source page for this originals stream")
        committed = json.loads(row[2]) if row is not None else None
        current = _existing_page(target)
        binding, revisions = _read_marks(current, namespace)
        previous, recovered = _recover_previous(committed, namespace, revisions)
        result = _read(source, path, previous, format, origins, start_line, end_line, selected_message_id)
        response = {"ok": False, "page": str(target), "issues": result["issues"],
                    "observed": result["observed"], "cursor_committed": False}
        if result["issues"]:
            return response
        proposed = _position_without_rewind(previous, result["proposed_cursor"])
        originals = result["originals"]
        if originals:
            count = sum(len(history) for history in revisions.values())
            replacement = _append_bytes(current, binding, namespace, originals, proposed, count)
            _write_page(target, current, replacement)
            current = replacement
        if _existing_page(target) != current:
            raise BatchError("EXM source page changed during the import; run again")
        if proposed != committed:
            _save_cursor(db, stream, page_key, proposed)
        return {**response, "ok": True, "saved": len(originals), "recovered": recovered,
                "cursor_committed": True, "position": proposed["position"]}


def add_originals_parser(group):
    parser = group.add_parser("originals", help="Save selected native originals in EXM and resume incrementally")
    parser.add_argument("--format", choices=_FORMATS, required=True)
    parser.add_argument("--session", dest="session_id", required=True)
    parser.add_argument("--project", dest="project_id", required=True, help="Registered source project")
    parser.add_argument("--input", dest="input_file", required=True, help="Selected local export/API page")
    parser.add_argument("--page", required=True, help="Selected EXM Markdown page")
    parser.add_argument("--origins", dest="origins_file", help="JSON of reviewed native IDs and evidence")
    parser.add_argument("--work-group")
    parser.add_argument("--counterpart")
    parser.add_argument("--start-line", type=int, default=1)
    parser.add_argument("--end-line", type=int)
    parser.add_argument("--select-message", dest="selected_message_id")
    return parser


def execute_originals(args, installation):
    """Dispatch the originals subcommand from a registered CLI group."""
    return publish_originals(
        installation, format=args.format, session_id=args.session_id, project_id=args.project_id,
        input_file=args.input_file, page=args.page, origins_file=args.origins_file,
        work_group=args.work_group, counterpart=args.counterpart, start_line=args.start_line,
        end_line=args.end_line, selected_message_id=args.selected_message_id,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation-file")
    add_originals_parser(parser.add_subparsers(required=True))
    args = parser.parse_args()
    try:
        result = execute_originals(args, resolve_installation_path(args.installation_file))
    except (InstallationProblem, RegistryProblem, ValueError, OSError, sqlite3.Error, BadZipFile) as exc:
        result = {"ok": False, "error": str(exc), "cursor_committed": False}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
