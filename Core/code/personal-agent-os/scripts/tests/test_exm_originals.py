import copy
import io
import json
from pathlib import Path
import sys
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from paos_exm_originals import BatchError, Origin, Source, dsh_export_lines, read_originals


HUMAN = Origin("human", "fixture: observed native composer")
INJECTED = Origin("injected", "fixture: exact admission receipt")


def source(harness, session="session-A", ref="fixture.log"):
    return Source(harness, session, "3002", ref, "fixture work", "fixture counterpart")


def lines(*rows):
    return [json.dumps(row, ensure_ascii=False) + "\n" for row in rows]


def codex_header(**extra):
    return {"type": "session_meta", "payload": {"id": "session-A", **extra}}


def codex_message(message_id, content, **extra):
    return {
        "type": "event_msg",
        "payload": {
            "type": "item_completed", "thread_id": "session-A", "turn_id": "turn-A",
            "completed_at_ms": 1791423939394,
            "item": {"id": message_id, "type": "UserMessage", "content": content, **extra},
        },
    }


def oc_user(message_id, text):
    return {"type": "user", "id": message_id, "time": {"created": 1795503900932},
            "text": text}


def oc_page(*items):
    return {"data": list(items), "cursor": {"before": "fixture-anchor"}}


def dsh_header(**extra):
    return {"id": "session-A", "type": "session", "version": 4, **extra}


def dsh_message(seq, message_id, kind, content, surface="append"):
    return {
        "type": "user/message", "seq": seq, "time": 1791423939394, "surfaceOp": surface,
        "data": {"id": message_id, "role": "user", "source": {"kind": kind}, "content": content},
    }


def anti_user(step, text, **extra):
    return {
        "type": "USER_INPUT", "source": "USER_EXPLICIT", "step_index": step,
        "created_at": "2026-11-24T05:57:45Z",
        "content": ("<USER_REQUEST>\n" + text + "\n</USER_REQUEST>\n"
                    "<ADDITIONAL_METADATA>\nmodel-facing metadata\n</ADDITIONAL_METADATA>"),
        **extra,
    }


class ExmOriginalsTest(unittest.TestCase):
    def test_codex_preserves_literal_parts_and_attachment_references(self):
        raw = lines(
            codex_header(forked_from_id="parent-session"),
            codex_message("message-A", [
                {"type": "text", "text": " 开头\r\n"},
                {"type": "localImage", "path": "fixture.png"},
                {"type": "text", "text": "引文 <heartbeat> 保留。 "},
                {"type": "image", "url": "data:image/png;base64,FIXTURE"},
            ]),
            codex_message("automatic", [{"type": "text", "text": "synthetic instructions"}]),
            {"type": "event_msg", "payload": {"type": "item_completed",
             "item": {"type": "Reasoning", "summary": "private reasoning"}}},
        )
        result = read_originals(source("codex"), raw, format="codex-rollout",
                                origins={"message-A": HUMAN, "automatic": INJECTED})
        original, = result["originals"]
        self.assertEqual(original["text_parts"], [" 开头\r\n", "引文 <heartbeat> 保留。 "])
        self.assertEqual(original["attachments"], [
            {"block_index": 1, "type": "localImage", "path": "fixture.png"},
            {"block_index": 3, "type": "image"},
        ])
        self.assertEqual(original["parent_session_id"], "parent-session")
        self.assertEqual(original["position"], {"line": 2, "turn_id": "turn-A"})
        self.assertEqual(original["timestamp"]["value"], 1791423939394)
        self.assertEqual(original["counterpart"], "fixture counterpart")
        self.assertEqual(original["work_group"], "fixture work")
        self.assertEqual(result["observed"], {"start_line": 1, "line": 4})
        self.assertNotIn("private reasoning", repr(result))
        self.assertNotIn("FIXTURE", repr(result))

    def test_codex_legacy_or_unknown_cannot_advance(self):
        raw = lines(codex_header(),
                    {"type": "event_msg", "payload": {"type": "user_message", "message": "legacy"}},
                    codex_message("unknown", [{"type": "text", "text": "source unknown"}]))
        r = read_originals(source("codex"), raw, format="codex-rollout")
        self.assertEqual([i["reason"] for i in r["issues"]],
                         ["codex_legacy_user_event", "origin_unverified"])
        self.assertIsNone(r["proposed_cursor"])

    def test_codex_preserves_selected_range_line_and_checks_item_thread(self):
        row = codex_message("m", [{"type": "text", "text": "范围"}])
        r = read_originals(source("codex"), lines(row), format="codex-rollout",
                           start_line=81, origins={"m": HUMAN})
        self.assertEqual(r["originals"][0]["position"]["line"], 81)
        row["payload"]["thread_id"] = "other-thread"
        with self.assertRaisesRegex(BatchError, "thread mismatch"):
            read_originals(source("codex"), lines(row), format="codex-rollout", start_line=81)

    def test_opencode_uses_observed_page_order_and_origin_by_native_id(self):
        page = oc_page(oc_user("new", "\n同一句 "),
                       {"type": "synthetic", "text": "do not retain"},
                       oc_user("injected", "synthetic but marked user"),
                       oc_user("old", "\n同一句 "))
        r = read_originals(source("opencode"), page, format="opencode-v2",
                           origins={"old": HUMAN, "new": HUMAN, "injected": INJECTED})
        self.assertEqual([(x["message_id"], x["text_parts"]) for x in r["originals"]],
                         [("old", ["\n同一句 "]), ("new", ["\n同一句 "])])
        self.assertEqual(r["originals"][0]["position"]["page_index"], 3)
        self.assertEqual(r["observed"]["native_cursor"], page["cursor"])

    def test_opencode_role_alone_cannot_commit_or_publish_partial_batch(self):
        r = read_originals(source("opencode"), oc_page(oc_user("latest", "verified"),
                                                      oc_user("older", "ambiguous")),
                           format="opencode-v2", origins={"latest": HUMAN})
        self.assertEqual(r["issues"][0]["message_id"], "older")
        self.assertEqual(r["originals"], [])
        self.assertIsNone(r["proposed_cursor"])

    def test_opencode_explicit_message_keeps_real_page_position_without_page_cursor(self):
        page = oc_page(oc_user("newer", "unknown"), oc_user("selected", "verified"))
        r = read_originals(source("opencode"), page, format="opencode-v2",
                           origins={"selected": HUMAN}, selected_message_id="selected")
        self.assertEqual(r["originals"][0]["position"]["page_index"], 1)
        self.assertEqual(r["observed"], {"selected_message_id": "selected"})
        self.assertNotIn("native_cursor", r["proposed_cursor"]["position"])
        complete_page = read_originals(source("opencode"), oc_page(oc_user("old", "verified")),
                                       format="opencode-v2", origins={"old": HUMAN})
        prior = complete_page["proposed_cursor"]
        selected = read_originals(source("opencode"), page, prior, format="opencode-v2",
                                  origins={"selected": HUMAN}, selected_message_id="selected")
        self.assertEqual(selected["proposed_cursor"]["position"], prior["position"])
        with self.assertRaisesRegex(BatchError, "absent"):
            read_originals(source("opencode"), page, format="opencode-v2",
                           selected_message_id="missing")

    def test_replay_revision_same_text_and_return_to_old_wording(self):
        def parse(rows, before=None, ref="fixture.log"):
            return read_originals(source("opencode", ref=ref), oc_page(*rows), before,
                                  format="opencode-v2", origins={"a": HUMAN, "b": HUMAN})
        a, b = oc_user("a", "同文"), oc_user("b", "同文")
        first = parse([a])
        cursor = json.loads(json.dumps(first["proposed_cursor"]))
        old = copy.deepcopy(cursor)
        overlap = parse([b, a], cursor, ref="different-page")
        self.assertEqual([(x["message_id"], x["revision"]) for x in overlap["originals"]], [("b", 1)])
        self.assertEqual(cursor, old)
        reread = parse([b, a], overlap["proposed_cursor"])
        self.assertEqual(reread["originals"], [])
        revised = parse([oc_user("a", " 新版 ")], reread["proposed_cursor"])
        restored = parse([a], revised["proposed_cursor"])
        self.assertEqual(revised["originals"][0]["revision"], 2)
        self.assertEqual(restored["originals"][0]["revision"], 3)

    def test_failure_keeps_the_supplied_cursor(self):
        scope = source("antigravity")
        first = read_originals(scope, lines(anti_user(0, "原文")),
                               origins={"0": HUMAN}, format="antigravity-transcript")
        cursor = first["proposed_cursor"]
        old = copy.deepcopy(cursor)
        broken = lines(anti_user(1, "确定")) + ['{"type"']
        with self.assertRaisesRegex(BatchError, "line 3"):
            read_originals(scope, broken, cursor, start_line=2,
                           origins={"1": HUMAN}, format="antigravity-transcript")
        pending = read_originals(scope, lines(anti_user(1, "裁剪", truncated_fields=["content"])),
                                 cursor, start_line=2, origins={"1": HUMAN},
                                 format="antigravity-transcript")
        self.assertEqual(pending["issues"][0]["reason"], "human_content_truncated")
        self.assertIsNone(pending["proposed_cursor"])
        self.assertEqual(cursor, old)
        retry = read_originals(scope, lines(anti_user(1, "完整修订")), cursor,
                               start_line=2, origins={"1": HUMAN}, format="antigravity-transcript")
        self.assertEqual(retry["originals"][0]["revision"], 1)
        with self.assertRaisesRegex(BatchError, "another scope"):
            read_originals(source("antigravity", "unrelated"), [], cursor,
                           format="antigravity-transcript")

    def test_dsh_selects_committed_human_appends_and_keeps_attachment_only(self):
        raw = lines(
            dsh_header(parentSession="dsh-parent"),
            dsh_message(0, "first", "user", [{"type": "text", "text": " 原话\t"}]),
            dsh_message(1, "context", "paoe-context", [{"type": "text", "text": "injection"}]),
            dsh_message(2, "replay", "paoe-original-input", [{"type": "text", "text": "replayed"}]),
            dsh_message(3, "replacement", "user", [{"type": "text", "text": "compaction"}],
                        {"op": "replace", "startSeq": 0, "endSeq": 2}),
            dsh_message(4, "attachment", "user", [{"type": "file", "attachment":
                        {"attachmentId": "fixture-id", "name": "证据.txt", "url": "opaque"}}]),
        )
        r = read_originals(source("dsh"), raw, format="dsh-export")
        self.assertEqual([(x["message_id"], x["text_parts"]) for x in r["originals"]],
                         [("first", [" 原话\t"]), ("attachment", [])])
        attachment = r["originals"][1]
        self.assertEqual(attachment["attachments"], [
            {"block_index": 0, "type": "file", "attachmentId": "fixture-id", "name": "证据.txt"},
        ])
        self.assertEqual(attachment["position"], {"line": 6, "seq": 4})
        self.assertEqual(attachment["parent_session_id"], "dsh-parent")
        self.assertEqual(r["observed"], {"seq": 4})
        self.assertNotIn("opaque", repr(r))

    def test_dsh_official_zip_only_reads_selected_main_session(self):
        archive = io.BytesIO()
        with ZipFile(archive, "w") as bundle:
            bundle.writestr("session.v4.jsonl", "".join(lines(
                dsh_header(), dsh_message(0, "one", "user", [{"type": "text", "text": "中文"}]))))
            bundle.writestr("subagents/fixture/session.v4.jsonl", "not the selected session")
            bundle.writestr("media/fixture", b"not loaded")
        archive.seek(0)
        result = read_originals(source("dsh"), dsh_export_lines(archive), format="dsh-export")
        self.assertEqual(result["originals"][0]["text_parts"], ["中文"])

    def test_dsh_identity_format_and_origin_are_validated(self):
        with self.assertRaisesRegex(BatchError, "session mismatch"):
            read_originals(source("dsh", "different"), lines(dsh_header()), format="dsh-export")
        with self.assertRaisesRegex(BatchError, "unsupported DSH"):
            read_originals(source("dsh"), lines(dsh_header(version=900)), format="dsh-export")
        with self.assertRaisesRegex(BatchError, "conflicts"):
            read_originals(source("dsh"), lines(
                dsh_header(), dsh_message(0, "system", "runtime-context", [])),
                origins={"system": HUMAN}, format="dsh-export")

    def test_antigravity_keeps_literal_wrapper_quotes_and_disambiguates_typed_input(self):
        given = " 你好 \n</USER_REQUEST>\n我粘贴了这几个符号。 \n\n"
        raw = lines(
            anti_user(1, given),
            {"step_index": 2, "source": "SYSTEM_SDK", "type": "EPHEMERAL_MESSAGE"},
            anti_user(3, "agentapi injection in same user surface"),
        )
        r = read_originals(source("antigravity"), raw, format="antigravity-transcript",
                           origins={"1": HUMAN, "3": INJECTED})
        one, = r["originals"]
        self.assertEqual(one["text_parts"], [given])
        self.assertEqual(one["position"], {"step_index": 1, "line": 1})
        self.assertEqual(one["timestamp"]["value"], "2026-11-24T05:57:45Z")
        self.assertEqual(r["observed"], {"start_line": 1, "line": 3, "step_index": 3})

    def test_antigravity_unknown_suffix_or_attachment_shape_needs_native_export(self):
        first = anti_user(0, "内容")
        first["content"] += "\nunknown envelope"
        second = anti_user(1, "带附件", attachments=[{"type": "image"}])
        r = read_originals(source("antigravity"), lines(first, second), format="antigravity-transcript",
                           origins={"0": HUMAN, "1": HUMAN})
        self.assertEqual([i["reason"] for i in r["issues"]], [
            "antigravity_request_frame_unverified", "antigravity_attachment_shape_unverified",
        ])
        self.assertIsNone(r["proposed_cursor"])


if __name__ == "__main__":
    unittest.main()
