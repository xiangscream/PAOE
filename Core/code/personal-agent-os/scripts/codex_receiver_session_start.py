"""Prepare the caller's *own* registered Codex receiver.

Manual prepare, SessionStart (including compact) and UserPromptSubmit use the same Home/Contact and STOP
checks. Current thread identity comes from the host environment; this module
refuses a caller-supplied target override or another Home's credentials.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

from paos_attention_service import AttentionServiceProblem, _registry_projects_root
from paos_contact import load_native_targets
from paos_home import HomeProblem, project_agent_home, rooter_home
from paos_installation import InstallationProblem, load_installation_descriptor, resolve_installation_path
from paos_registry import ProjectRegistry
from paos_workstation import WorkstationProblem, posix_windows_drive_locator
from runtime_injection import InjectionError
from wakeup_native.codex_receiver import ReceiverError, record_lifecycle, reusable_owned_runtime, retire_owned_runtime


def registered_target(thread_id, descriptor):
    """Read registered Project/Rooter Contacts, then validate the matching Home."""
    try:
        registry = _registry_projects_root(descriptor)
    except AttentionServiceProblem as problem:
        if problem.code != "attention_projects_registry_missing":
            raise
        registry = None  # An installation Rooter does not require a Project.
    matches = []
    projects = ProjectRegistry(Path(descriptor["path"])) if registry else None
    project_views = [projects.read(p.stem) for p in sorted(registry.glob("*.json"))] if registry else []
    targets = load_native_targets(Path(descriptor["source_root"]), installation_path=descriptor["path"]) or {}
    for project in project_views:
        root_locator = project.get("root_path")
        if not root_locator:
            continue  # Unhoused projects have no Project Home or Contact root.
        root = Path(posix_windows_drive_locator(root_locator))
        for agent_id, target in targets.items():
            if agent_id not in project.get("homes", []):
                continue
            if target.get("runtime") == "codex" and target.get("session_id") == thread_id:
                home = project_agent_home(project=project, agent_id=agent_id)
                matches.append((home, target))
    rooter_locator = descriptor.get("rooter_home")
    if rooter_locator:
        root = Path(posix_windows_drive_locator(rooter_locator)).expanduser()
        # Same Home id/root contract as the public Rooter Contact route.
        target = targets.get("rooter-001")
        if target and target.get("runtime") == "codex" and target.get("session_id") == thread_id:
            home = rooter_home(home_path=root, home_id="rooter-001")
            matches.append((home, target))
    if len(matches) != 1:
        raise ValueError("contact_thread_not_registered" if not matches else "contact_thread_ambiguous")
    return matches[0]


def _is_prepare_event(event):
    name = event.get("hook_event_name")
    return name == "UserPromptSubmit" or name == "SessionStart" and event.get("source") in {"startup", "resume", "compact"}


def observe_hook_entry(event, *, installation_path=None, entrypoint='receiver'):
    """Record that a registered hook reached Python before the Owner environment guard."""
    thread = event.get("session_id")
    if not _is_prepare_event(event) or not isinstance(thread, str) or not thread:
        return
    descriptor = load_installation_descriptor(installation_path or resolve_installation_path())
    try:
        home, target = registered_target(thread, descriptor)
    except ValueError as exc:
        if str(exc) == "contact_thread_not_registered":
            return
        raise
    locator = (target.get("extension") or {}).get("receiver_runtime_file")
    if not isinstance(locator, str) or not locator:
        return home
    runtime = Path(posix_windows_drive_locator(locator))
    if not runtime.is_absolute() or not runtime.parent.is_dir():
        return home
    owner = os.environ.get("CODEX_THREAD_ID")
    with runtime.with_name(runtime.name + ".lifecycle.jsonl").open("a", encoding="utf-8") as stream:
        record_lifecycle(stream, "owner_hook_entered", entrypoint=entrypoint, hook=event["hook_event_name"],
                         parent_pid=os.getppid(),
                         source=event.get("source") if event["hook_event_name"] == "SessionStart" else None,
                         owner_thread_present=bool(owner), owner_thread_matches=owner == thread,
                         desktop_connection_present=bool(os.environ.get("CODEX_APP_TOOLS_PIPE_PATH")))
    return home


def prepare(event):
    if not _is_prepare_event(event):
        return "receiver_prepare_skipped: unsupported_event"
    return prepare_current(event=event)


def prepare_current(*, event=None, update=False, installation_path=None, expected_home=None):
    """Use a native Hook's Owner, or the manual caller's Desktop environment."""
    thread_id = os.environ.get("CODEX_THREAD_ID", "")
    receiver_environment = None
    if event is not None:
        if not _is_prepare_event(event):
            return "receiver_prepare_skipped: unsupported_event"
        event_thread = event.get("session_id")
        if not isinstance(event_thread, str) or not event_thread.strip():
            return "receiver_prepare_skipped: event_thread_missing"
        if thread_id and event_thread != thread_id:
            return "receiver_prepare_skipped: event_thread_mismatch"
        if not thread_id:
            thread_id = event_thread
            # A trusted native Hook supplies its own identity before shell tools exist.
            # Scope it to this preparation and the receiver child, not process globals.
            receiver_environment = dict(os.environ, CODEX_THREAD_ID=thread_id)
    if not thread_id or not os.environ.get("CODEX_APP_TOOLS_PIPE_PATH"):
        return "receiver_prepare_skipped: original_desktop_environment_missing"
    if os.name != "nt":
        return "receiver_prepare_skipped: windows_desktop_required"

    descriptor = load_installation_descriptor(installation_path or resolve_installation_path())
    home, target = registered_target(thread_id, descriptor)
    if expected_home is not None and any(home.get(field) != expected_home.get(field)
                                         for field in ("home_kind", "project_id", "home_id", "home_path")):
        return "receiver_prepare_skipped: resume_target_not_owner"
    # Bind establishes Contact configuration; concurrent Owner resumes are readers.
    extension = target.get("extension") or {}
    locators = [extension.get("receiver_runtime_file"), target.get("stop_file"), extension.get("windows_python")]
    if not all(isinstance(item, str) and item.strip() for item in locators):
        raise ValueError("receiver_binding_incomplete: complete the original Home's receiver registration, then --prepare-current")
    runtime, stop, python = [Path(posix_windows_drive_locator(item)) for item in locators]
    if not all(item.is_absolute() for item in (runtime, stop, python)):
        return "receiver_prepare_skipped: registered_receiver_locators_not_absolute"
    if stop.exists():
        return "receiver_prepare_skipped: original_STOP_present"
    if update:
        retire_owned_runtime(runtime, stop)
    elif runtime.exists():
        pid = reusable_owned_runtime(runtime, stop, environment=receiver_environment)
        if pid is not None:
            return f"receiver_prepare_reused: {home['home_id']} PID {pid}; original receiver unchanged."
    scripts = Path(posix_windows_drive_locator(descriptor["source_root"])) / "scripts"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    with Path(f"{runtime}.prepare-{stamp}.stdout.log").open("wb") as stdout, Path(f"{runtime}.prepare-{stamp}.stderr.log").open("wb") as stderr:
        process = subprocess.Popen(
            [str(python), "-X", "utf8", "-B", "-m", "wakeup_native.codex_receiver",
             "--runtime-file", str(runtime), "--stop-file", str(stop)],
            cwd=scripts, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_BREAKAWAY_FROM_JOB,
            env=receiver_environment,
        )
    action = "update" if update else "prepare"
    return f"receiver_{action}_started: {home['home_id']} PID {process.pid}; read readiness through wake status."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group()
    commands.add_argument("--prepare-current", action="store_true",
                        help="Prepare only this Desktop caller's registered receiver; no hook event required.")
    commands.add_argument("--update-current", action="store_true",
                          help="Update only this Desktop Owner's verified receiver; keep STOP and unknown instances.")
    args = parser.parse_args()
    exit_code = 0
    output = {}
    try:
        if args.update_current:
            message = prepare_current(update=True)
        elif args.prepare_current:
            message = prepare_current()
        else:
            event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
            home = None
            try:
                home = observe_hook_entry(event)
            except (OSError, ValueError, KeyError, InstallationProblem, AttentionServiceProblem,
                    HomeProblem, WorkstationProblem) as exc:
                print(f"receiver_hook_observation_unavailable: {type(exc).__name__}", file=sys.stderr)
            message = prepare(event)
            if (home and event.get("hook_event_name") == "SessionStart"
                    and message == "receiver_prepare_skipped: original_desktop_environment_missing"):
                command = ("attention rooter-show --resume" if home["home_kind"] == "rooter"
                           else f"orient {home['project_id']} {home['home_id']} --resume")
                output["hookSpecificOutput"] = {
                    "hookEventName": "SessionStart",
                    "additionalContext": (
                        "本会话已登记 PAOE 接收器。请用本人 ENTRY 中的安装 CLI 前缀，在当前原 Desktop 工具环境运行 "
                        f"`{command}` 完成复工，并继续阅读当前输入。"
                    ),
                }
    except (OSError, UnicodeError, ValueError, KeyError, HomeProblem, InstallationProblem,
            AttentionServiceProblem, WorkstationProblem, ReceiverError, InjectionError) as exc:
        detail = f"{exc.code}: {exc}" if isinstance(exc, ReceiverError) else str(exc)
        message = f"receiver_prepare_unavailable: {detail}"
        exit_code = 1 if args.prepare_current or args.update_current else 0
    print(json.dumps({"systemMessage": message, **output}))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
