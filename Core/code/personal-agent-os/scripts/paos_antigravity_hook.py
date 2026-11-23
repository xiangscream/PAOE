"""Adapt Antigravity's documented hooks to PAOE's registered Home context."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from paos_contact import runtime_contact
from paos_home import HomeProblem, project_agent_home
from paos_installation import InstallationProblem, resolve_installation_path
from paos_registry import ProjectRegistry, RegistryProblem
from paos_workstation import WorkstationProblem


SCRIPTS = Path(__file__).resolve().parent
READ_TIMEOUT_SECONDS = 8


class ContextProblem(RuntimeError):
    """A registered conversation could not obtain the required originals."""


def context_text(result, agent_id):
    """Accept the common reader's exact Home and complete originals."""
    try:
        view = json.loads(result.stdout)
    except (UnicodeError, ValueError) as exc:
        raise ContextProblem("无法读取 PAOE 上下文回执。") from exc
    if (not isinstance(view, dict) or view.get("schema") != "paoe-context/v1"
            or view.get("home_id") != agent_id or view.get("reason") != "request"):
        raise ContextProblem("PAOE 上下文回执与当前工位或读取类型不符。")
    missing = view.get("missing")
    if isinstance(missing, list) and missing:
        names = [f"{item['kind']}（{item['reason']}）" for item in missing
                 if isinstance(item, dict) and "kind" in item and "reason" in item]
        raise ContextProblem("缺少本次必读原件。" + "、".join(names))
    documents = view.get("documents")
    if (result.returncode != 0 or view.get("ok") is not True or missing != []
            or not isinstance(documents, list) or not documents):
        raise ContextProblem("PAOE 未返回完整的必读原件。")
    if any(not isinstance(doc, dict) or any(
        not isinstance(doc.get(key), str) or not doc[key].strip()
        for key in ("kind", "path", "body")
    ) for doc in documents):
        raise ContextProblem("PAOE 必读原件内容或定位不完整。")
    return "\n\n".join(
        f"[{doc['kind']}] {doc['path']}\n{doc['body']}" for doc in documents
    )


def call_context(installation_path, arguments, *, timeout):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "paos.py"), "--installation-file", str(installation_path),
         "--json", "context", *arguments],
        stdin=subprocess.DEVNULL, capture_output=True,
        encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=timeout, check=False,
    )


def observe_stop(request, installation_path, agent_id, cat_url):
    execution = request.get("executionNum")
    if type(execution) is not int or execution < 0:
        print("PAOE Antigravity Stop: missing native execution number.", file=sys.stderr)
        return {"decision": "stop"}
    event = f"antigravity:{request['conversationId']}:{execution}"
    # The native execution number also increments on a hook-induced reentry.
    # Use the common no-continuation path until a stable turn ID is available.
    args = ["stop", agent_id, "--event", event, "--reentry"]
    if cat_url:
        args.extend(["--cat-url", cat_url])
    try:
        result = call_context(installation_path, args, timeout=3)
    except (subprocess.TimeoutExpired, OSError, UnicodeError):
        print("PAOE Antigravity Stop: common stop action unavailable.", file=sys.stderr)
    else:
        if result.returncode:
            print("PAOE Antigravity Stop: common stop action failed.", file=sys.stderr)
    return {"decision": "stop"}


def run_hook(event, request, project_id, agent_id, installation_path, cat_url=None):

    session_id = request["conversationId"]
    project = ProjectRegistry(installation_path).read(project_id)
    home = project_agent_home(project=project, agent_id=agent_id)
    contact = runtime_contact(Path(home["project_root"]), agent_id)
    if contact["runtime"] != "antigravity" or contact["native_session_id"] != session_id:
        return {}
    if event == "Stop":
        return observe_stop(request, installation_path, agent_id, cat_url)

    try:
        result = call_context(installation_path, ["read", agent_id, "--reason", "request"],
                              timeout=READ_TIMEOUT_SECONDS)
        text = context_text(result, agent_id)
    except subprocess.TimeoutExpired:
        message = "读取 PAOE 必读原件超时。"
    except (OSError, UnicodeError):
        message = "PAOE 上下文读取命令不可用。"
    except ContextProblem as exc:
        message = str(exc)
    else:
        return {"injectSteps": [{"ephemeralMessage": "[PAOE 本次必读原文]\n\n" + text}]}
    return {
        "terminationBehavior": "terminate",
        "injectSteps": [{"errorMessage": {"userMessage": message}}],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", choices=("PreInvocation", "Stop"), required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--installation-file")
    parser.add_argument("--cat-url", help="Registered CAT endpoint for Stop presence updates.")
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin.buffer)
        if not isinstance(payload, dict) or not isinstance(payload.get("conversationId"), str) or not payload["conversationId"]:
            raise ValueError("Hook input requires a conversationId.")
        response = run_hook(args.event, payload, args.project, args.agent,
                            resolve_installation_path(args.installation_file), args.cat_url)
    except (HomeProblem, InstallationProblem, RegistryProblem, WorkstationProblem,
            OSError, ValueError) as exc:
        print(f"PAOE Antigravity hook: {getattr(exc, 'code', str(exc))}", file=sys.stderr)
        return 1
    sys.stdout.buffer.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
