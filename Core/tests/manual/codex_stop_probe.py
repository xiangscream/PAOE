"""Manual Desktop-only probe. Never install this as the global Stop handler."""
import argparse
import json
from pathlib import Path
import sys
import subprocess


def probe(event, session, evidence, stop_file):
    if event.get("session_id") != session or event.get("hook_event_name") != "Stop":
        return {}
    if stop_file.exists():
        return {}
    if not event.get("turn_id") or type(event.get("stop_hook_active")) is not bool:
        raise ValueError("真实 Stop 缺少 turn_id 或 stop_hook_active")
    previous = [json.loads(line) for line in evidence.read_text(encoding="utf-8").splitlines()] if evidence.exists() else []
    # This finite sequence is the experiment protocol, not a business loop cap.
    number = len(previous) + 1
    response = ({"decision": "block", "reason": f"PAOE-STOP-PROBE-{'A' if number == 1 else 'B'}：请仅回复此标记，然后结束本回合。"}
                if number <= 2 else {})
    record = {"ordinal": number, "event": {key: event.get(key) for key in (
        "session_id", "turn_id", "hook_event_name", "stop_hook_active", "event_id", "hook_run_id")},
        "response": response}
    evidence.parent.mkdir(parents=True, exist_ok=True)
    with evidence.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=False) + "\n")
    return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--stop-file", type=Path, required=True)
    parser.add_argument("--write-project-config", type=Path,
                        help="Prepare a new isolated project's normal .codex/hooks.json; never changes trust")
    args = parser.parse_args()
    if args.write_project_config:
        command = subprocess.list2cmdline([sys.executable, "-X", "utf8", str(Path(__file__).resolve()),
            "--session", args.session, "--evidence", str(args.evidence.resolve()),
            "--stop-file", str(args.stop_file.resolve())])
        path = args.write_project_config / ".codex/hooks.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as output:
            json.dump({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": command,
                                                         "timeout": 10}]}]}}, output, ensure_ascii=False, indent=2)
        print(json.dumps({"project_hook": str(path.resolve()), "trust": "normal_application_review_required"}))
        return
    event = json.load(sys.stdin)
    response = probe(event, args.session, args.evidence, args.stop_file)
    print(json.dumps(response, ensure_ascii=False))


if __name__ == "__main__":
    main()
