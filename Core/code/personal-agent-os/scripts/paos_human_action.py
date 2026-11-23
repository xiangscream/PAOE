"""Capture the one Human decision. There is no non-interactive affirmative input."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from paos_team import decision_subject, read_action, receipt_path, team_path


def _display(action, subject, explanation):
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText

    labels = {
        "open-plan": "通过计划并开房",
        "approve-roles": "通过角色安排",
        "save-role": "保存角色并提醒本人",
        "accept-goal": "验收目标并关闭专用房",
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


def _persist(path, receipt):
    """Publish only a complete receipt. The replay key is the original UI request."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / (path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        os.link(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def confirm(data, action, ident, payload, resolve_home, client):
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
            _persist(path, receipt)
        except FileExistsError:
            original = read_action(data, ident)
            if original["action"] != action or original["input"] != payload:
                raise ValueError("确认 ID 冲突")
    route = "/api/team/open" if action == "open-plan" else team_path(payload["room"]) + "/" + action
    return {
        "ok": True,
        "receipt_id": ident,
        "applied": client.request("POST", route, {"receipt_id": ident}),
    }
