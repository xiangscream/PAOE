"""Read-only projection of personal TODO tasks by work-group labels."""
from __future__ import annotations

from typing import Any, Iterable

WORK_GROUP = "work-group:"
CAT_ROLE = "cat-role:"
CAT_ROOM = "cat-room:"


def _group_name(source_refs: Iterable[Any]) -> str | None:
    names: list[str] = []
    for ref in source_refs:
        text = str(ref or "")
        if text.startswith(WORK_GROUP):
            name = text[len(WORK_GROUP):].strip()
            if name and name not in names:
                names.append(name)
    # One explicit group is usable. Multiple distinct groups are ambiguous;
    # keep the task in the ungrouped bucket instead of guessing one.
    return names[0] if len(names) == 1 else None


def _room(source_ref: Any) -> str | None:
    text = str(source_ref or "").strip()
    if text.startswith(CAT_ROOM):
        room = text[len(CAT_ROOM):].strip()
        return room or None
    if text.startswith(CAT_ROLE):
        room = text[len(CAT_ROLE):].strip()
        # enroll writes cat-role:<room>; a second /<home> spelling is not valid.
        return room if room and "/" not in room else None
    return None


def project_groups(tasks: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return [{name, rooms, tasks}] without changing any Task.

    Named groups keep first-appearance order; the ungrouped bucket (name=None)
    is last. Rooms are unique and keep first-appearance order. Task objects are
    the original dictionaries, so callers can still read their source refs and
    results without a second TODO model.
    """
    named: dict[str, dict[str, Any]] = {}
    ungrouped = {"name": None, "rooms": [], "tasks": []}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        name = _group_name(task.get("source_refs") or [])
        group = named.get(name) if name is not None else ungrouped
        if group is None:
            group = {"name": name, "rooms": [], "tasks": []}
            named[name] = group
        group["tasks"].append(task)
        for ref in task.get("source_refs") or []:
            room = _room(ref)
            if room and room not in group["rooms"]:
                group["rooms"].append(room)
    groups = list(named.values())
    if ungrouped["tasks"]:
        groups.append(ungrouped)
    return groups
