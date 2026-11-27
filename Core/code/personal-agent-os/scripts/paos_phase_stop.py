"""Project one native stop onto room presence; business completion remains explicit."""

from pathlib import Path
from urllib.parse import quote, urlencode

from paos_content import changes_db
from paos_todo import read_todo


def on_stop(data, home, *, staff, event, task_id, interrupted, reentry, waiting_human,
            client=None, presence_only=False):
    if not event.strip():
        raise ValueError("停止事件需要原宿主事件 ID")
    answer = _stop_decision(data, home, event=event, task_id=task_id,
                            interrupted=interrupted, reentry=reentry,
                            waiting_human=waiting_human, presence_only=presence_only)
    offline = []
    if answer["action"] == "stop" and client is not None:
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
    answer.update(rooms_offline=offline, presence_checked=client is not None and answer["action"] == "stop")
    return answer


def _stop_decision(data, home, *, event, task_id, interrupted, reentry,
                   waiting_human, presence_only):
    answer = {
        "ok": True,
        "schema": "paoe-context-stop/v1",
        "event": event,
        "action": "stop",
        "reason": "no_current_task",
    }
    if interrupted or reentry or waiting_human:
        answer["reason"] = "interrupted" if interrupted else "reentry" if reentry else "waiting_human"
        return answer
    if presence_only:
        answer["reason"] = "presence_only"
        return answer
    todo = read_todo(Path(home["home_path"]) / "TODO.md")
    current = todo["current"]
    active = [r.removeprefix("task:") for r in current["context_refs"] if r.startswith("task:")]
    focused = task_id or (active[0] if len(active) == 1 else "")
    # Current waiting belongs to its selected responsibility. Inflight is a
    # free-text description, never proof that the native executor is occupied.
    available = executable_tasks(todo, task_id)
    if not available:
        answer["reason"] = "waiting" if any(t["state"] in {"doing", "todo", "waiting"} for t in todo["tasks"]) else "no_current_task"
        return answer
    task = available[0]
    with changes_db(data) as db:
        inserted = db.execute(
            "INSERT OR IGNORE INTO stop_events(home,event) VALUES(?,?)", (home["home_id"], event)
        ).rowcount
    if inserted:
        answer.update(
            action="continue",
            reason="unfinished_current",
            task_id=task["id"],
            next_action=(current["next_action"] if task["id"] == focused and current["next_action"].strip()
                         else f"读取本人 TODO 的 {task['id']}（{task['title']}）及其原输入，接续已授权责任。"),
        )
    else:
        answer["reason"] = "already_observed"
    return answer


def executable_tasks(todo, task_id=''):
    """Shared business eligibility, independent of native Stop or busy state."""
    current = todo['current']
    active = [r.removeprefix('task:') for r in current['context_refs'] if r.startswith('task:')]
    focused = task_id or (active[0] if len(active) == 1 else '')
    available = [t for t in todo['tasks'] if t['state'] in {'doing', 'todo'}
                 and not t['waiting'] and not (t['id'] == focused and current['waiting'])]
    available.sort(key=lambda t: (t['state'] != 'doing', t['id'] != focused))
    return available
