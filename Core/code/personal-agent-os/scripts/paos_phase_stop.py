"""Project one native stop onto room presence; business completion remains explicit."""

from pathlib import Path
from urllib.parse import quote, urlencode

from paos_content import changes_db
from paos_todo import read_todo


def on_stop(data, home, *, staff, event, task_id, interrupted, reentry, waiting_human, client=None):
    if not event.strip():
        raise ValueError("停止事件需要原宿主事件 ID")
    offline = []
    if client is not None:
        rooms = client.request("GET", "/api/rooms?" + urlencode({"home_id": staff}))["rooms"]
        for room in rooms:
            if room["status"] != "closed" and room.get("presence") == "online":
                client.request(
                    "POST",
                    "/api/rooms/"
                    + quote(room["id"], safe="")
                    + "/members/"
                    + quote(staff, safe="")
                    + "/progress",
                    {"presence": "offline"},
                )
                offline.append(room["id"])
    answer = {
        "ok": True,
        "schema": "paoe-context-stop/v1",
        "event": event,
        "rooms_offline": offline,
        "presence_checked": client is not None,
        "action": "stop",
        "reason": "no_current_task",
    }
    if interrupted or reentry or waiting_human:
        answer["reason"] = "interrupted" if interrupted else "reentry" if reentry else "waiting_human"
        return answer
    todo = read_todo(Path(home["home_path"]) / "TODO.md")
    current = todo["current"]
    if not task_id:
        active = [r.removeprefix("task:") for r in current["context_refs"] if r.startswith("task:")]
        task_id = active[0] if len(active) == 1 else ""
    task = next((t for t in todo["tasks"] if t["id"] == task_id), None)
    if task is None or task["state"] != "doing":
        return answer
    if current["waiting"] or current["inflight"] or task["waiting"]:
        answer["reason"] = "waiting"
        return answer
    with changes_db(data) as db:
        inserted = db.execute(
            "INSERT OR IGNORE INTO stop_events(home,event) VALUES(?,?)", (home["home_id"], event)
        ).rowcount
    if inserted:
        answer.update(
            action="continue",
            reason="unfinished_current",
            task_id=task_id,
            next_action=current["next_action"],
        )
    else:
        answer["reason"] = "already_observed"
    return answer
