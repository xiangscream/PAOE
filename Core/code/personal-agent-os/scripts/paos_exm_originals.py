"""Read one explicitly selected EXM source batch and propose its next cursor.

Transport, authorization and durable publication belong to the caller. Source
references and origin attestations must identify the exact supplied records.
"""

from dataclasses import dataclass
import hashlib
import json
import re
from zipfile import ZipFile


@dataclass(frozen=True)
class Source:
    harness: str
    session_id: str
    project_id: str
    source_ref: str
    work_group: str | None = None
    counterpart: str | None = None

    def namespace(self):
        return [self.harness, self.session_id, self.project_id, self.work_group]


@dataclass(frozen=True)
class Origin:
    kind: str
    evidence_ref: str


class BatchError(ValueError):
    """The supplied scope, format or checkpoint cannot be read safely."""


_NON_HUMAN = {"injected", "system", "automation", "forwarded"}
_CODEX_ATTACHMENTS = {"image", "localImage", "file", "mention", "skill"}
_ANTIGRAVITY_BEGIN = "<USER_REQUEST>\n"
_ANTIGRAVITY_END = "\n</USER_REQUEST>"
_ANTIGRAVITY_SUFFIX = re.compile(
    r"\n<ADDITIONAL_METADATA>\n.*?\n</ADDITIONAL_METADATA>"
    r"(?:\n<USER_SETTINGS_CHANGE>\n.*?\n</USER_SETTINGS_CHANGE>)?\s*",
    re.DOTALL,
)


def _require(condition, diagnostic):
    if not condition:
        raise BatchError(diagnostic)


def _id(value):
    _require(isinstance(value, str) and bool(value.strip()), "missing native identity")
    return value


def _index(value):
    _require(type(value) is int and value >= 0, "invalid native position")
    return value


def _timestamp(value, basis):
    if value is None:
        return {"value": None, "basis": "unavailable"}
    _require(type(value) is int or isinstance(value, str), "invalid native timestamp")
    return {"value": value, "basis": basis}


def _jsonl(lines, start_line):
    for line_no, line in enumerate(lines, start_line):
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise BatchError(f"invalid JSONL at line {line_no}") from exc
        _require(isinstance(record, dict), f"expected a JSON object at line {line_no}")
        yield line_no, record


def _blocks(blocks, attachment_types):
    _require(isinstance(blocks, list), "native content blocks missing")
    parts = []
    attachments = []
    for index, block in enumerate(blocks):
        kind = block["type"]
        if kind == "text":
            _require(isinstance(block["text"], str), "invalid native text block")
            parts.append(block["text"])
            continue
        _require(kind in attachment_types, f"unsupported Human block at index {index}")
        ref = block.get("attachment", block)
        pointer = {"block_index": index, "type": kind}
        for key in ("attachmentId", "id", "name", "path", "mediaType"):
            if isinstance(ref.get(key), str):
                pointer[key] = ref[key]
        # Source position locates a remote/embedded asset without copying its URL or bytes.
        attachments.append(pointer)
    return parts, attachments


def _entry(message_id, position, timestamp, parts, attachments, origin, parent_session_id=None):
    return {
        "message_id": message_id,
        "position": position,
        "timestamp": timestamp,
        "text_parts": parts,
        "attachments": attachments,
        "origin": {"kind": "human", "evidence_ref": origin.evidence_ref},
        "parent_session_id": parent_session_id,
    }


def _review(message_id, position, origins, issues, native_origin=None):
    origin = origins.get(message_id, native_origin)
    if origin is None:
        issues.append({"reason": "origin_unverified", "message_id": message_id, "position": position})
        return None
    _require(isinstance(origin, Origin) and
             origin.kind in _NON_HUMAN | {"human"} and
             bool(origin.evidence_ref), "invalid origin attestation")
    _require(native_origin is None or native_origin.kind == "human" or origin.kind != "human",
             "attestation conflicts with native non-Human origin")
    return origin if origin.kind == "human" else None


def _complete(record, message_id, position, issues):
    if not (record.get("truncated") or record.get("truncated_fields")
            or record.get("contentTruncated") or record.get("textTruncated")):
        return True
    issues.append({"reason": "human_content_truncated", "message_id": message_id, "position": position})
    return False


def _codex_item(item, position, timestamp, origins, issues, parent):
    message_id = _id(item["id"])
    origin = _review(message_id, position, origins, issues)
    if origin is None or not _complete(item, message_id, position, issues):
        return None
    parts, attachments = _blocks(item["content"], _CODEX_ATTACHMENTS)
    return _entry(message_id, position, timestamp, parts, attachments, origin, parent)


def _codex_rollout(source, lines, origins, issues, start_line):
    entries = []
    end = start_line - 1
    parent = None
    for end, row in _jsonl(lines, start_line):
        payload = row["payload"]
        if row["type"] == "session_meta":
            _require(payload["id"] == source.session_id, "Codex rollout session mismatch")
            parent = payload.get("forked_from_id")
        elif row["type"] == "event_msg" and payload.get("type") == "item_completed":
            item = payload["item"]
            if item.get("type") != "UserMessage":
                continue
            _require(payload["thread_id"] == source.session_id, "Codex item thread mismatch")
            candidate = _codex_item(
                item, {"line": end, "turn_id": payload["turn_id"]},
                _timestamp(payload.get("completed_at_ms"), "Codex item_completed.completed_at_ms (epoch ms)"),
                origins, issues, parent,
            )
            if candidate is not None:
                entries.append(candidate)
        elif row["type"] == "event_msg" and payload.get("type") == "user_message":
            # Legacy mirrors have no native item ID with an exact content block stream.
            issues.append({"reason": "codex_legacy_user_event", "position": {"line": end}})
    return entries, {"start_line": start_line, "line": end}


def _opencode(source, page, origins, issues, selected_message_id):
    entries = []
    cursor = page["cursor"]
    selected = False
    for index, row in reversed(list(enumerate(page["data"]))):
        if row["type"] != "user" or (selected_message_id is not None and row["id"] != selected_message_id):
            continue
        message_id = _id(row["id"])
        if selected_message_id is not None:
            _require(not selected, "duplicate selected OpenCode message ID")
            selected = True
        position = {"page_index": index, "native_type": row["type"]}
        if row.get("sessionID") is not None:
            _require(row["sessionID"] == source.session_id, "OpenCode message session mismatch")
        origin = _review(message_id, position, origins, issues)
        if origin is None or not _complete(row, message_id, position, issues):
            continue
        _require(isinstance(row["text"], str), "OpenCode user text missing")
        parts = [row["text"]]
        attachments = []
        if row.get("attachments"):
            issues.append({"reason": "opencode_attachment_shape_unverified", "message_id": message_id,
                           "position": position})
            continue
        stamp = _timestamp(row["time"]["created"], "OpenCode time.created (epoch ms)")
        entries.append(_entry(message_id, position, stamp, parts, attachments, origin))
    if selected_message_id is not None:
        _require(selected, "selected OpenCode user message is absent from this page")
        return entries, {"selected_message_id": selected_message_id}
    return entries, {"rows": len(page["data"]), "native_cursor": cursor}


def _dsh(source, lines, origins, issues):
    records = _jsonl(lines, 1)
    _, header = next(records, (None, {}))
    _require(header.get("type") == "session" and header.get("id") == source.session_id,
             "DSH export session mismatch or missing header")
    _require(header.get("version") == 4, "unsupported DSH physical export version")
    parent = header.get("parentSession")
    entries = []
    last_seq = None
    for line, row in records:
        seq = _index(row["seq"])
        _require(last_seq is None or seq > last_seq, "DSH export sequence is not increasing")
        last_seq = seq
        if row["type"] != "user/message" or row["surfaceOp"] != "append":
            continue
        data = row["data"]
        message_id = _id(data["id"])
        position = {"line": line, "seq": seq}
        native_kind = data["source"]["kind"]
        _id(native_kind)
        native_origin = Origin(
            "human" if native_kind == "user" else "injected",
            f"DSH data.source.kind={native_kind}",
        )
        origin = _review(message_id, position, origins, issues, native_origin)
        if origin is None or not _complete(row, message_id, position, issues):
            continue
        parts, attachments = _blocks(data["content"], {"image", "file"})
        entries.append(_entry(
            message_id, position, _timestamp(row["time"], "DSH event.time (epoch ms)"),
            parts, attachments, origin, parent,
        ))
    return entries, {"seq": last_seq}


def _antigravity(lines, origins, issues, start_line):
    entries = []
    last_step = None
    end = start_line - 1
    for end, row in _jsonl(lines, start_line):
        step = _index(row["step_index"])
        _require(last_step is None or step > last_step, "Antigravity steps are not increasing")
        last_step = step
        if row["type"] != "USER_INPUT":
            continue
        position = {"line": end, "step_index": step}
        message_id = str(step)
        if row["source"] != "USER_EXPLICIT":
            continue
        origin = _review(message_id, position, origins, issues)
        if origin is None or not _complete(row, message_id, position, issues):
            continue
        content = row["content"]
        head, marker, suffix = content.rpartition(_ANTIGRAVITY_END)
        if not head.startswith(_ANTIGRAVITY_BEGIN) or not marker or (
            suffix and _ANTIGRAVITY_SUFFIX.fullmatch(suffix) is None
        ):
            issues.append({"reason": "antigravity_request_frame_unverified", "message_id": message_id,
                           "position": position})
            continue
        if row.get("attachments"):
            issues.append({"reason": "antigravity_attachment_shape_unverified", "message_id": message_id,
                           "position": position})
            continue
        parts = [head[len(_ANTIGRAVITY_BEGIN):]]
        entries.append(_entry(
            message_id, position, _timestamp(row.get("created_at"), "Antigravity step.created_at (ISO 8601)"),
            parts, [], origin,
        ))
    return entries, {"start_line": start_line, "line": end, "step_index": last_step}


def dsh_export_lines(archive):
    """Yield the one main session JSONL from a selected official ZIP. No extraction."""
    with ZipFile(archive) as bundle:
        matches = [entry for entry in bundle.infolist()
                   if re.fullmatch(r"session(?:\.v\d+)?\.jsonl", entry.filename)]
        _require(len(matches) == 1, "DSH ZIP must contain one main session log")
        with bundle.open(matches[0]) as log:
            for line_no, line in enumerate(log, 1):
                try:
                    yield line.decode("utf-8-sig" if line_no == 1 else "utf-8")
                except UnicodeError as exc:
                    raise BatchError(f"invalid DSH JSONL encoding at line {line_no}") from exc


def read_originals(source, native, previous=None, *, format, origins=None, start_line=1,
                   selected_message_id=None):
    """Read one coherent batch. The caller commits the proposed cursor after writing.

    OpenCode input is its native page object. The other formats take an
    iterable of JSONL lines. Supply caller-verified origin by native ID
    where the runtime only identifies a user surface. A blocked read yields no
    publishable originals and no proposed cursor. Text parts preserve their native
    boundaries and contents. Attachments are pointers into the original source.
    OpenCode supports taking one attested user message from a page without
    claiming traversal of the page.
    """
    _id(source.session_id)
    _id(source.project_id)
    _id(source.source_ref)
    _require(type(start_line) is int and start_line > 0, "invalid JSONL start line")
    harness = {
        "codex-rollout": "codex", "opencode-v2": "opencode",
        "dsh-export": "dsh", "antigravity-transcript": "antigravity",
    }
    _require(format in harness and harness[format] == source.harness, "source format/harness mismatch")
    if selected_message_id is not None:
        _require(format == "opencode-v2", "selected message is only supported for OpenCode pages")
        _id(selected_message_id)
    namespace = source.namespace()
    if previous is not None:
        _require(previous.get("version") == 1 and previous.get("namespace") == namespace and
                 isinstance(previous.get("messages"), dict), "cursor belongs to another scope")
    origins = origins or {}
    issues = []
    try:
        if format == "codex-rollout":
            candidates, observed = _codex_rollout(source, native, origins, issues, start_line)
        elif format == "opencode-v2":
            candidates, observed = _opencode(source, native, origins, issues, selected_message_id)
        elif format == "dsh-export":
            candidates, observed = _dsh(source, native, origins, issues)
        else:
            candidates, observed = _antigravity(native, origins, issues, start_line)
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise BatchError(f"malformed {format} batch") from exc

    if issues:
        return {"originals": [], "issues": issues, "observed": observed, "proposed_cursor": None}

    known = {} if previous is None else previous["messages"].copy()
    originals = []
    batch_ids = set()
    for entry in candidates:
        message_id = entry["message_id"]
        _require(message_id not in batch_ids, "duplicate native message ID in one batch")
        batch_ids.add(message_id)
        # Position can change across pages. Only source text and native attachment references version it.
        canonical = json.dumps([entry["text_parts"], entry["attachments"]], ensure_ascii=False,
                               sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        prior = known.get(message_id)
        if prior is not None and prior["fingerprint"] == fingerprint:
            continue
        revision = 1 if prior is None else prior["revision"] + 1
        known[message_id] = {"fingerprint": fingerprint, "revision": revision}
        originals.append({
            **entry, "revision": revision, "harness": source.harness, "session_id": source.session_id,
            "source_ref": source.source_ref, "project_id": source.project_id,
            "work_group": source.work_group, "counterpart": source.counterpart,
        })
    position = {"source_ref": source.source_ref, "format": format, **observed}
    if selected_message_id is not None and previous is not None:
        prior_position = previous.get("position", {})
        if prior_position.get("format") == format and "native_cursor" in prior_position:
            position = prior_position.copy()
    proposed = {"version": 1, "namespace": namespace, "messages": known, "position": position}
    return {"originals": originals, "issues": [], "observed": observed, "proposed_cursor": proposed}
