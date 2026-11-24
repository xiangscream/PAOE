"""A stage result belongs to the member's existing Task. The Data receipt resumes partial writes."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from paos_content import (changes_db, db_path, original_version, pack, record_version,
                          save_snapshot, scoped_file, snapshot_original)
from paos_todo import parse_todo, render_todo, write_todo


def task_snapshot(home, task_id):
    path = Path(home["home_path"]) / "TODO.md"
    raw = path.read_bytes()
    doc = parse_todo(raw.decode("utf-8-sig"))
    if (doc["home_kind"], doc["home_id"], doc["project_id"]) != (
        home["home_kind"],
        home["home_id"],
        home["project_id"],
    ):
        raise ValueError("TODO 身份与登记工位不一致")
    task = next((item for item in doc["tasks"] if item["id"] == task_id), None)
    if task is None:
        raise ValueError(f"本人 TODO 没有任务 {task_id}")
    return path, hashlib.sha256(raw).hexdigest(), doc, task


def render(doc):
    return render_todo(
        home_kind=doc["home_kind"],
        home_id=doc["home_id"],
        project_id=doc["project_id"],
        pinned=doc["pinned"],
        tasks=doc["tasks"],
        **doc["current"],
    )


def with_refs(existing, extra):
    return list(dict.fromkeys([*existing, *extra]))


def _apply(doc, task, req, marker):
    if marker in task["source_refs"]:
        return False
    if task["state"] in {"done", "cancelled"}:
        raise ValueError(f"任务 {task['id']} 已结束，不能写新阶段")
    task.update(
        result=req["result"],
        artifact_ref=req["artifacts"][0],
        waiting=req["waiting"],
        state="waiting" if req["waiting"] else "doing",
    )
    task["source_refs"] = with_refs(
        task["source_refs"], [marker, *req["intents"], *req["artifacts"][1:]]
    )
    current = doc["current"]
    anchor = "task:" + task["id"]
    if req["current"] or anchor in current["context_refs"]:
        if anchor not in current["context_refs"]:
            current["objective"] = task["title"]
            remaining = [ref for ref in current["context_refs"] if not ref.startswith("task:")]
            current["context_refs"] = with_refs([anchor, *req["intents"]], remaining)
        current.update(next_action=req["next"] or req["waiting"], waiting=req["waiting"], inflight="")
        current["result_refs"] = with_refs(current["result_refs"], req["artifacts"])
        current["updated_at"] = datetime.now(timezone.utc).isoformat()
    elif req["next"]:
        task["result"] += " 下一步：" + req["next"]
    return True


def deliver(
    data, home, *, task_id, operation, artifacts, intents, result, next_action, waiting, current,
    source_roots=()
):
    if not operation or len(operation) > 120 or any(c.isspace() for c in operation):
        raise ValueError("交付 ID 需要稳定且不含空白字符")
    if not artifacts or not intents or not result.strip() or not (bool(next_action) ^ bool(waiting)):
        raise ValueError("请给出成果、意图来源、阶段结果，以及下一步或等待")
    req = dict(
        task=task_id,
        artifacts=list(artifacts),
        intents=list(intents),
        result=result,
        next=next_action,
        waiting=waiting,
        current=current,
    )
    encoded, ident = pack(req), (home["home_id"], operation)
    marker = "stage:" + operation
    root = Path(home["project_root"] or home["home_path"])
    if not db_path(data).exists():
        _, _, doc, task = task_snapshot(home, task_id)
        _apply(doc, task, req, marker)
        render(doc)
        for locator in (*artifacts, *intents):
            scoped_file(root, locator, source_roots=source_roots)

    def receipt(sources, replay):
        return {
            "ok": True,
            "schema": "paoe-stage-delivery/v1",
            "home_id": ident[0],
            "task_id": task_id,
            "operation_id": operation,
            "replayed": replay,
            "result": result,
            "sources": sources,
        }

    with changes_db(data) as db:
        db.execute("BEGIN IMMEDIATE")
        prior = db.execute("SELECT * FROM stages WHERE home=? AND operation=?", ident).fetchone()
        if prior and prior["request"] != encoded:
            raise ValueError("同一阶段交付 ID 已用于其他内容")
        if prior:
            sources = json.loads(prior["sources"])
            if prior["finished"]:
                return receipt(sources, True)
        else:
            _, _, doc, task = task_snapshot(home, task_id)
            if not _apply(doc, task, req, marker):
                raise ValueError("已有阶段关联但缺少原交付记录")
            render(doc)  # Validate the whole candidate before reserving this delivery.
            sources = {}
            for kind, locators in (("artifact", artifacts), ("intent", intents)):
                for locator in locators:
                    path = scoped_file(root, locator, source_roots=source_roots)
                    version, body = snapshot_original(path)
                    save_snapshot(db, version, body)
                    sources[str(path)] = {"kind": kind, "version": version}
            db.execute(
                "INSERT INTO stages(home,operation,request,sources) VALUES(?,?,?,?)",
                (*ident, encoded, pack(sources)),
            )
            db.commit()  # Durable recovery point before the independent TODO writer.
            db.execute("BEGIN IMMEDIATE")
        path, before, doc, task = task_snapshot(home, task_id)
        fresh = _apply(doc, task, req, marker)
        if fresh:
            for source, info in sources.items():
                if original_version(Path(source)) != info["version"]:
                    raise ValueError(f"阶段登记后原件已变：{source}")
            write_todo(path, render(doc), expected_fingerprint=before)
        for source, info in sources.items():
            record_version(db, source, info["version"], info["kind"], "stage")
            if not fresh:
                current_version, body = snapshot_original(Path(source)) if Path(source).is_file() else ("removed", None)
                if current_version != info["version"]:
                    record_version(db, source, current_version, info["kind"], "reconcile", body=body)
        db.execute("UPDATE stages SET finished=1 WHERE home=? AND operation=?", ident)
    return receipt(sources, False)
