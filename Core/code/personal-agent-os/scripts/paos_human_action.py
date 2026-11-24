"""Record one Human decision and apply it once, from conversation or optional UI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import quote

from paos_team import decision_subject, publish_receipt, read_action, receipt_path, team_path


CHOICES = {"approve", "reject", "revise", "defer"}


def _apply(client, action, payload, ident):
    if action == "close-room":
        return client.request("POST", "/api/rooms/" + quote(payload["room"], safe="") + "/close",
                              {"receipt_id": ident})
    route = "/api/team/open" if action == "open-plan" else team_path(payload["room"]) + "/" + action
    return client.request("POST", route, {"receipt_id": ident})


def review(action, payload, resolve_home, client):
    subject, explanation = decision_subject(action, payload, resolve_home, client)
    return {"ok": True, "action": action, "input": payload,
            "subject": subject, "explanation": explanation}


def record_decision(data, action, ident, payload, decision, resolve_home, client):
    """The recorder attributes an explicit decision; code never infers approval from prose."""
    fields = {"choice", "channel", "recorded_by", "source_ref", "quote", "subject"}
    if not isinstance(decision, dict) or set(decision) != fields:
        raise ValueError("决定需要 choice/channel/recorded_by/source_ref/quote/subject")
    if (not isinstance(decision["choice"], str) or decision["choice"] not in CHOICES
            or not isinstance(decision["channel"], str) or decision["channel"] not in {"conversation", "ui"}):
        raise ValueError("请明确通过、拒绝、要求修改或稍后决定，以及对话或 UI 来源")
    if any(not isinstance(decision[k], str) or not decision[k].strip()
           for k in ("recorded_by", "source_ref", "quote")):
        raise ValueError("请记录决定的原话、来源与记录人")
    subject = decision["subject"]
    if not isinstance(subject, dict) or not subject or not isinstance(payload, dict):
        raise ValueError("决定需要准确的审阅对象与操作输入")
    path = receipt_path(data, ident)
    channel = decision["channel"] + "-human-decision"
    metadata = {k: decision[k] for k in ("choice", "recorded_by", "source_ref", "quote")}
    replayed = path.is_file()
    if replayed:
        old = read_action(data, ident, require_approval=False)
        if (old["action"], old["input"], old["subject"], old["channel"], old.get("decision")) != (
                action, payload, subject, channel, metadata):
            raise ValueError("原决定 ID 对应不同的操作、内容或决定")
    else:
        if decision["choice"] == "approve":
            current, _ = decision_subject(action, payload, resolve_home, client)
            if current != subject:
                raise ValueError("决定对应的内容已变化，请先对齐受影响的差异")
        receipt = {"schema": "paoe-human-action/v1", "id": ident, "channel": channel,
                   "action": action, "input": payload, "subject": subject,
                   "decision": metadata, "created_at": datetime.now(timezone.utc).isoformat()}
        try:
            publish_receipt(path, receipt)
        except FileExistsError:
            old = read_action(data, ident, require_approval=False)
            if {k: old.get(k) for k in receipt if k != "created_at"} != {
                    k: v for k, v in receipt.items() if k != "created_at"}:
                raise ValueError("决定 ID 冲突")
            replayed = True
    if decision["choice"] != "approve":
        state = {"reject": "rejected", "revise": "changes_requested", "defer": "deferred"}
        return {"ok": True, "receipt_id": ident, "state": state[decision["choice"]],
                "applied": None, "replayed": replayed}
    return {"ok": True, "receipt_id": ident, "replayed": replayed,
            "applied": _apply(client, action, payload, ident)}


def _display(action, subject, explanation):
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText

    labels = {
        "open-plan": "通过计划并开房",
        "approve-roles": "通过角色安排",
        "save-role": "保存角色并提醒本人",
        "accept-goal": "验收目标并关闭专用房",
        "close-room": "关闭本讨论房，保留历史",
    }
    window = tk.Tk()
    window.title("PAOE · " + labels[action])
    window.geometry("720x520")
    ttk.Label(window, text=labels[action], padding=10).pack(anchor="w")
    view = ScrolledText(window, wrap="word")
    view.pack(fill="both", expand=True, padx=10)
    view.insert("end", explanation + "\n\n" + json.dumps(subject, ensure_ascii=False, indent=2))
    view.configure(state="disabled")
    choice = []

    def accept():
        choice.append(True)
        window.destroy()

    bar = ttk.Frame(window, padding=10)
    bar.pack(fill="x")
    ttk.Button(bar, text="取消", command=window.destroy).pack(side="left")
    ttk.Button(bar, text=labels[action], command=accept).pack(side="right")
    window.protocol("WM_DELETE_WINDOW", window.destroy)
    window.mainloop()
    return bool(choice)


def confirm(data, action, ident, payload, resolve_home, client, *, decision=None):
    if decision is not None:
        return record_decision(data, action, ident, payload, decision, resolve_home, client)
    path = receipt_path(data, ident)
    if path.is_file():
        original = read_action(data, ident)
        if original["action"] != action or original["input"] != payload:
            raise ValueError("原确认 ID 对应不同的操作")
    else:
        subject, explanation = decision_subject(action, payload, resolve_home, client)
        try:
            import tkinter

            accepted = _display(action, subject, explanation)
        except ImportError as exc:
            raise ValueError("当前安装没有图形确认入口") from exc
        except tkinter.TclError as exc:
            raise ValueError("当前会话无法显示 Human 确认窗口") from exc
        if not accepted:
            return {"ok": True, "state": "cancelled"}
        latest, _ = decision_subject(action, payload, resolve_home, client)
        if latest != subject:
            raise ValueError("确认期间原安排已变化，请重新查看")
        receipt = {
            "schema": "paoe-human-action/v1",
            "id": ident,
            "channel": "native-human-confirmation",
            "action": action,
            "input": payload,
            "subject": subject,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            publish_receipt(path, receipt)
        except FileExistsError:
            original = read_action(data, ident)
            if original["action"] != action or original["input"] != payload:
                raise ValueError("确认 ID 冲突")
    return {
        "ok": True,
        "receipt_id": ident,
        "applied": _apply(client, action, payload, ident),
    }
