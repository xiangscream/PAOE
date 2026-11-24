"""Opt-in real OpenCode V2 context test, using a disposable Home and loopback model."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener
import base64
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time

SOURCE = Path(__file__).resolve().parents[1] / "code/personal-agent-os"
sys.path.insert(0, str(SOURCE / "scripts"))
from paos_todo import render_todo, update_todo_current

SUMMARY = """## Objective
- Continue the isolated task.

## Requirements
- Local only.

## Decisions
- Preserve the input.

## Work State
### Completed
- Read fixture.

### Active
- Continue task.

### Blocked
- (none)

## Next Move
1. Continue fixture.

## Relevant Files
- (none).

## Important Context
- (none)."""


def save(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(contents, ensure_ascii=False), encoding="utf-8")


def wait_for(read, predicate, description):
    for _ in range(100):
        result = read()
        if predicate(result):
            return result
        time.sleep(.15)
    raise AssertionError(f"{description}: {str(result)[:1000]}")


class LocalModel(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, status, kind, data):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        assert self.path == "/api/rooms?home_id=S001", self.path
        pause = self.server.cat_pause
        if pause:
            self.server.cat_pause = None
            entered, release = pause
            entered.set()
            assert release.wait(10), "test did not release CAT room lookup"
        try:
            self.reply(200, "application/json", b'{"rooms":[{"id":"room-fixture","status":"active","presence":"online"}]}')
        except (BrokenPipeError, ConnectionResetError):
            if pause is None:
                raise

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/rooms/room-fixture/members/S001/progress":
            self.server.cat_updates.append(body)
            self.reply(200, "application/json", b'{"ok":true}')
            return
        assert self.path == "/v1/chat/completions", self.path
        messages = body["messages"]
        tail = json.dumps(messages[-1], ensure_ascii=False)
        compacting = "<template>" in tail
        refused = not compacting and "LOCAL_CAPACITY_REFUSAL" in tail
        wire = json.dumps(messages, ensure_ascii=False)
        observed = {"compaction": compacting, "refused": refused, "request": "<compaction>" if compacting else tail,
                    "original_1": "REQUIRED_ORIGINAL_FIRST" in wire,
                    "original_2": "REQUIRED_ORIGINAL_CHANGED" in wire,
                    "original_3": "REQUIRED_ORIGINAL_AFTER_COMPACT" in wire}
        self.server.observed.append(observed)
        if "STOP_DURING_MODEL_FIXTURE" in tail:
            self.server.stop_during_model.write_text("STOP", encoding="utf-8")
        if "NEW_ACTIVE_TURN_FIXTURE" in tail:
            entered, release = self.server.model_pause
            entered.set()
            assert release.wait(10), "test did not release the newer native turn"
        if refused:
            error = {"error": {"message": "This model maximum context length exceeded.",
                               "type": "invalid_request_error", "code": "context_length_exceeded"}}
            self.reply(400, "application/json", json.dumps(error).encode())
            return
        if compacting and self.server.change_original:
            self.server.original.write_text("REQUIRED_ORIGINAL_AFTER_COMPACT", encoding="utf-8")
            self.server.change_original = False
        if compacting and self.server.stop_during_compaction:
            self.server.stop_during_compaction.write_text("STOP", encoding="utf-8")
            self.server.stop_during_compaction = None
        answer = SUMMARY if compacting else "LOCAL_ASSISTANT_REPLY"
        chunks = [
            {"id": "fixture", "object": "chat.completion.chunk", "created": 1, "model": "fixture",
             "choices": [{"index": 0, "delta": {"role": "assistant", "content": answer}, "finish_reason": None}]},
            {"id": "fixture", "object": "chat.completion.chunk", "created": 1, "model": "fixture",
             "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
             "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
        ]
        data = "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n"
        self.reply(200, "text/event-stream", data.encode())


class IsolatedHost:
    def __init__(self, root, exe, provider_port):
        self.root, self.exe = root, exe
        self.password = secrets.token_urlsafe(32)
        self.opener = build_opener(ProxyHandler({}))
        self.work = root / "work"
        self.work.mkdir()
        self.config = root / "config/opencode/opencode.json"
        self.settings = {
            "model": "fixture-local/fixture", "enabled_providers": ["fixture-local"], "snapshots": False,
            "compaction": {"auto": False},
            "providers": {"fixture-local": {"package": "@opencode/ai/providers/openai-compatible",
                "settings": {"baseURL": f"http://127.0.0.1:{provider_port}/v1", "apiKey": "fixture"},
                "models": {"fixture": {"name": "Local fixture", "limit": {"context": 16384, "output": 1024}}}}},
        }

    @contextmanager
    def serve(self):
        save(self.config, self.settings)
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            self.origin = f"http://127.0.0.1:{reserved.getsockname()[1]}"
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith(
            ("OPENCODE_", "XDG_", "PAOS_", "OPENAI_", "ANTHROPIC_", "GOOGLE_", "DEEPSEEK_", "GEMINI_"))}
        for name in ("HOME", "USERPROFILE", "OPENCODE_TEST_HOME", "TMP", "TEMP", "APPDATA", "LOCALAPPDATA"):
            env[name] = str(self.root)
        for name in ("CONFIG", "DATA", "CACHE", "STATE"):
            env[f"XDG_{name}_HOME"] = str(self.root / name.lower())
        env.update(OPENCODE_PASSWORD=self.password, OPENCODE_DB=str(self.root / "native.db"),
                   OPENCODE_CONFIG=str(self.config), OPENCODE_DISABLE_FREE_MODELS="1",
                   OPENCODE_DISABLE_AUTOUPDATE="1", NO_PROXY="127.0.0.1")
        log = self.root / "host.log"
        with log.open("ab") as output:
            process = subprocess.Popen([self.exe, "serve", "--hostname", "127.0.0.1",
                                        "--port", self.origin.rsplit(":", 1)[1]], cwd=self.work,
                                       env=env, stdout=output, stderr=output,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                def info():
                    if process.poll() is not None:
                        raise RuntimeError(log.read_text(encoding="utf-8", errors="replace")[-3000:])
                    try:
                        return self.call("GET", "/api/info")
                    except URLError:
                        return {}
                details = wait_for(info, lambda data: "version" in data, "isolated host start")
                assert details["pid"] == process.pid, details
                assert Path(details["paths"]["tmp"]).is_relative_to(self.root), details
                yield details["version"]
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=10)

    def call(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        auth = base64.b64encode(("opencode:" + self.password).encode()).decode()
        request = Request(self.origin + path, method=method, data=data,
                          headers={"Authorization": "Basic " + auth, "Content-Type": "application/json"})
        with self.opener.open(request, timeout=4) as response:
            return json.load(response)

    def session(self, title):
        return self.call("POST", "/api/session", {"location": {"directory": str(self.work)},
                          "model": {"providerID": "fixture-local", "id": "fixture"}, "title": title})["data"]

    def transcript(self, sid):
        return self.call("GET", f"/api/session/{sid}/message")["data"]

    def admit(self, sid, text):
        mid = "msg_" + secrets.token_hex(16)
        receipt = self.call("POST", f"/api/session/{sid}/prompt", {"id": mid, "text": text})["data"]
        assert receipt["id"] == mid and receipt["sessionID"] == sid, receipt
        return mid

    def submit(self, sid, text):
        before = {item["id"] for item in self.transcript(sid)}
        mid = self.admit(sid, text)
        wait_for(lambda: self.transcript(sid), lambda rows: any(
            row["type"] == "idle" and row["id"] not in before for row in rows), "native idle")
        return mid


def prepare_core(root, sid, core_source):
    project, data = root / "project", root / "paoe-data"
    home = project / "Workstations/S001"
    home.mkdir(parents=True)
    original = project / "input.md"
    original.write_text("REQUIRED_ORIGINAL_FIRST", encoding="utf-8")
    for path, text in [(project / "AGENTS.md", "[共同背景](background.md)"),
                       (project / "background.md", "Fixture shared context"),
                       (project / "TEAM.md", "### S001\nContext test"),
                       (project / "INDEX.md", "Isolated project"),
                       (home / "ENTRY.md", "Read the originals")]:
        path.write_text(text, encoding="utf-8")
    todo = home / "TODO.md"
    todo.write_text(render_todo(home_kind="project_agent", home_id="S001", project_id="3002",
        objective="Keep the fixture isolated", next_action="Read project originals",
        tasks=[dict(id="T-001", title="Keep the fixture isolated", source_refs=["input.md"], state="doing"),
               dict(id="T-002", title="Verify operator stop", state="doing")]),
        encoding="utf-8")
    update_todo_current(todo, {"context_refs": ["task:T-001"], "waiting": "Test fixture does not request Stop correction"})
    installation = root / "installation.json"
    numbers = root / "staff.json"
    save(numbers, {"S001": "S001"})
    save(installation, {"schema": "paos-installation/v1", "source_root": str(core_source),
                         "data_root": str(data), "library_roots_config": str(root / "libraries.json"),
                         "agent_numbers_config": str(numbers), "rooter_home": str(root / "rooter")})
    save(data / "project-registry/projects/3002.json", {"schema": "paos-project-registry/v1",
         "id": "3002", "root_path": str(project), "homes": ["S001"], "coordinator_home_id": "S001"})
    stop = root / "native.stop"
    driver = root / "driver.json"
    save(driver, {"api_version": 2, "stop_file": str(stop)})
    bind = subprocess.run([sys.executable, "-X", "utf8", "-B", str(core_source / "scripts/paos.py"),
                           "--installation-file", str(installation), "--json", "wake", "bind", "3002", "S001",
                           "--driver", "opencode", "--native-session-id", sid, "--driver-config", str(driver)],
                          capture_output=True, text=True, encoding="utf-8")
    assert bind.returncode == 0, (bind.stdout, bind.stderr)
    return installation, original, stop, todo, data / "runtime/opencode-context/S001/events.jsonl"


def check_stopped_presence(host, sid, provider, stop, todo):
    observations = {}

    def ends_offline(prompt, label):
        count, before = len(provider.observed), len(provider.cat_updates)
        host.submit(sid, prompt)
        wait_for(lambda: provider.cat_updates[before:], bool, label)
        assert provider.cat_updates[before:] == [{"presence": "offline"}], label
        assert len(provider.observed) == count + 1, f"{label}: unexpected continuation"
        observations[label] = {"offline": 1, "automatic_continuations": 0}

    with host.serve():
        stop.write_text("STOP", encoding="utf-8")
        ends_offline("STOP_AT_ENTRY_FIXTURE", "stop_at_entry")
        stop.unlink()
        provider.stop_during_model = stop
        ends_offline("STOP_DURING_MODEL_FIXTURE", "stop_during_model")
        stop.unlink()
        update_todo_current(todo, {"context_refs": []})
        ends_offline("NO_CURRENT_TASK_FIXTURE", "no_current_task")

        update_todo_current(todo, {"context_refs": ["task:T-002"], "waiting": "Hold for fixture"})
        cat_entered, cat_release, new_entered, new_release = (threading.Event() for _ in range(4))
        provider.cat_pause = (cat_entered, cat_release)
        provider.model_pause = (new_entered, new_release)
        count, before = len(provider.observed), len(provider.cat_updates)
        try:
            host.submit(sid, "ENDING_TURN_FIXTURE")
            assert cat_entered.wait(5), "old turn did not reach CAT room lookup"
            host.admit(sid, "NEW_ACTIVE_TURN_FIXTURE")
            assert new_entered.wait(5), "newer turn did not reach the model"
            cat_release.set()
            assert not new_release.wait(.75)
            assert len(provider.cat_updates) == before, "old turn marked the newer active turn offline"
        finally:
            cat_release.set()
            new_release.set()
        wait_for(lambda: provider.cat_updates[before:], bool, "newer turn's own offline update")
        assert provider.cat_updates[before:] == [{"presence": "offline"}]
        assert len(provider.observed) == count + 2, "unexpected continuation during handoff"
        observations["superseded_turn"] = {"offline_while_new_turn_active": 0, "offline_after_new_turn": 1}
    return observations


def failure_probe(root, candidate):
    """Expose the review's user-tail snapshot while retaining the native event and wait."""
    probe = root / "failure-probe"
    evidence = root / "failure-probe.jsonl"
    save(probe / "package.json", {"name": "failure-probe", "version": "0.0.1", "type": "module",
                                 "exports": {".": "./index.js"}})
    (probe / "index.js").write_text(f"""
import {{ appendFile }} from 'node:fs/promises'
import plugin from {json.dumps((candidate / 'index.mjs').as_uri())}
const record = row => appendFile({json.dumps(str(evidence))}, JSON.stringify(row) + '\\n')
export default {{ ...plugin, setup: ctx => plugin.setup({{
  ...ctx,
  event: {{ ...ctx.event, async *subscribe(options) {{
    for await (const event of ctx.event.subscribe(options)) {{
      if (event.type === 'session.execution.failed') {{
        await record({{ event: event.type, session: event.data.sessionID }})
      }}
      yield event
    }}
  }} }},
  session: {{ ...ctx.session, async context(params) {{
    const history = await ctx.session.context(params)
    const user = history.findLastIndex(message => message.type === 'user')
    if (history[user]?.text !== 'MISSING_REQUIRED_USER_TAIL') return history
    const visible = history.slice(0, user + 1)
    await record({{ input: history[user].id, session: params.sessionID,
      native_tail: history.at(-1).type, probe_tail: visible.at(-1).type }})
    return visible
  }} }},
}}) }}
""", encoding="utf-8")
    return probe, evidence


def check(exe, expected, root, provider, core_source=None):
    provider.observed = []
    provider.change_original = False
    provider.stop_during_compaction = None
    provider.cat_updates = []
    provider.cat_pause = None
    host = IsolatedHost(root, exe, provider.server_port)
    with host.serve() as version:
        assert version == expected
        sid = host.session("Selected fixture session")["id"]
        other = host.session("Unselected fixture session")["id"]
    installation, original, stop, todo, journal = prepare_core(root, sid, core_source or SOURCE)
    provider.original = original
    later = root / "later"
    save(later / "package.json", {"name": "later-hook-fixture", "version": "0.0.1", "type": "module",
                                 "exports": {".": "./index.js"}})
    (later / "index.js").write_text("""export default { id: 'later-hook-fixture', async setup(ctx) {
      await ctx.session.hook('context', request => {
        const input = request.messages.findLast(message => message.role === 'user')
        if (request.sessionID === ctx.options.session && input?.content[0]?.text === 'LATER_HOOK_FIXTURE') {
          request.system = request.system.filter(part => !part.text.includes('REQUIRED_ORIGINAL_'))
        }
      })
    }}""", encoding="utf-8")
    adapter = SOURCE / "adapters/opencode"
    if core_source is not None:
        adapter, failure_evidence = failure_probe(root, adapter)
    host.settings["plugins"] = [{"package": adapter.as_posix(),
        "options": {"installation": str(installation), "python": sys.executable,
                    "sessions": {sid: {"project": "3002", "home": "S001",
                                       "requiredSources": ["input.md"], "recoverCapacity": True}}}},
        {"package": later.as_posix(), "options": {"session": sid}}]
    if core_source is not None:
        host.settings["plugins"][0]["options"]["catUrl"] = f"http://127.0.0.1:{provider.server_port}"

    def journal_rows():
        return [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()] if journal.exists() else []

    with host.serve() as version:
        host.submit(other, "UNSELECTED_FIXTURE")
        assert not provider.observed[-1]["original_1"]
        first = host.submit(sid, "SELECTED_FIRST_FIXTURE")
        assert provider.observed[-1]["original_1"] and "SELECTED_FIRST_FIXTURE" in provider.observed[-1]["request"], (
            journal_rows(), host.transcript(sid), (root / "host.log").read_text(encoding="utf-8", errors="replace")[-2000:])
        later_input = host.submit(sid, "LATER_HOOK_FIXTURE")
        assert not provider.observed[-1]["original_1"]
        assert any(row["action"] == "request_checked" and row.get("input") == later_input and
                   row["checkpoint"] == "OpenCode context" for row in journal_rows())
        original.write_text("REQUIRED_ORIGINAL_CHANGED", encoding="utf-8")
        presence_before = len(provider.cat_updates)
        host.submit(sid, "SOURCE_CHANGED_FIXTURE")
        assert provider.observed[-1]["original_2"] and not provider.observed[-1]["original_1"]
        if core_source is not None:
            wait_for(lambda: provider.cat_updates[presence_before:], bool, "changed source turn ends")
        original.unlink()
        count = len(provider.observed)
        presence_before = len(provider.cat_updates)
        host.submit(sid, "MISSING_REQUIRED_ORIGINAL")
        assert len(provider.observed) == count
        assert journal_rows()[-1]["action"] == "originals_unavailable"
        if core_source is not None:
            wait_for(lambda: provider.cat_updates, lambda updates: len(updates) > presence_before,
                     "failed request marks the selected Home offline")
            assert provider.cat_updates[presence_before:] == [{"presence": "offline"}]
            presence_before = len(provider.cat_updates)
            failed_input = host.submit(sid, "MISSING_REQUIRED_USER_TAIL")
            assert journal_rows()[-1]["action"] == "originals_unavailable"
            wait_for(lambda: provider.cat_updates[presence_before:], bool,
                     "native failure with user-tail snapshot marks the selected Home offline")
            assert provider.cat_updates[presence_before:] == [{"presence": "offline"}]
            assert len(provider.observed) == count, "failed inputs must make zero model requests"
            observations = [json.loads(line) for line in failure_evidence.read_text(encoding="utf-8").splitlines()]
            assert observations[-2] == {"event": "session.execution.failed", "session": sid}
            failure_presence = observations[-1]
            assert failure_presence["input"] == failed_input and failure_presence["session"] == sid
            assert failure_presence["probe_tail"] == "user"
            messages = host.transcript(sid)
            failure_presence.update(event=observations[-2]["event"], offline=1, model_requests=0,
                                    message_endpoint_first=messages[0]["type"],
                                    message_endpoint_last=messages[-1]["type"],
                                    message_endpoint_last_is_failed_input=messages[-1]["id"] == failed_input)
        else:
            failure_presence = {}
        original.write_text("REQUIRED_ORIGINAL_CHANGED", encoding="utf-8")

        provider.change_original = True
        count = len(provider.observed)
        refused = host.submit(sid, "LOCAL_CAPACITY_REFUSAL")
        wait_for(lambda: provider.observed[count:], lambda rows: len(rows) >= 3, "compaction and continuation")
        recovery = provider.observed[count:]
        assert len(recovery) == 3 and recovery[0]["refused"] and recovery[1]["compaction"]
        assert not any(recovery[1][key] for key in ("original_1", "original_2", "original_3"))
        assert recovery[2]["original_3"] and "T-001" in recovery[2]["request"]
        timeline = journal_rows()
        completed = [entry for entry in timeline if entry["action"] == "compaction_completed"]
        assert len(completed) == 1 and completed[0]["input"] == refused
        assert completed[0]["session"] == sid and completed[0]["task"] == "T-001"
        assert any(row["type"] == "user" and row["id"] == refused
                   for row in host.transcript(sid)), "original native input disappeared"
        assert any(entry["input"] == first for entry in timeline if entry["action"] == "request_checked")

    with host.serve():
        count = len(provider.observed)
        duplicate = host.submit(sid, "LOCAL_CAPACITY_REFUSAL again")
        wait_for(journal_rows, lambda rows: any(row.get("input") == duplicate and
                 row["action"] == "capacity_owner" for row in rows), "persisted recovery limit")
        assert len(provider.observed) == count + 1
        update_todo_current(todo, {"context_refs": ["task:T-002"]})
        provider.stop_during_compaction = stop
        count = len(provider.observed)
        stopped = host.submit(sid, "LOCAL_CAPACITY_REFUSAL new task")
        wait_for(journal_rows, lambda rows: any(row.get("input") == stopped and
                 row["action"] == "capacity_owner" for row in rows), "STOP during compaction")
        assert stop.exists() and len(provider.observed) == count + 2
        assert provider.observed[-1]["compaction"]
        count = len(provider.observed)
        host.submit(sid, "MANUAL_WHILE_STOPPED")
        assert len(provider.observed) == count + 1 and not provider.observed[-1]["original_3"]
        assert host.call("GET", f"/api/session/{sid}")["data"]["id"] == sid
        stop.unlink()
        update_todo_current(todo, {"waiting": "", "next_action": "STOP_CORRECTION_FIXTURE"})
        count = len(provider.observed)
        host.submit(sid, "SUCCESS_FOR_CORRECTION")
        wait_for(lambda: provider.observed[count:], lambda rows: len(rows) == 2, "single Stop correction")
        assert "STOP_CORRECTION_FIXTURE" in provider.observed[-1]["request"]
        wait_for(lambda: host.transcript(sid), lambda rows: rows[0]["type"] == "idle" and
                 len([r for r in rows if r["type"] == "user" and
                      r.get("text") == "STOP_CORRECTION_FIXTURE"]) == 1, "correction finished")
        assert len(provider.observed) == count + 2
    stopped_presence = check_stopped_presence(host, sid, provider, stop, todo) if core_source is not None else {}
    return {"version": version, "session": sid, "other_session": other, "selected": True,
            "native_model": "fixture-local/fixture", "missing_before_transport": True,
            "provider_capacity_refusal_then_compact": True, "durable_same_task_once": True,
            "new_original_after_compaction": True, "stop_preserved": True, "single_stop_correction": True,
            "later_hook_changes_wire_after_own_checkpoint": True,
            "paired_core_presence": core_source is not None,
            "stopped_presence": stopped_presence,
            "failure_presence": failure_presence,
            "wire": provider.observed, "journal": journal_rows()}


if __name__ == "__main__":
    executable, version = sys.argv[1:3]
    core = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else None
    provider = ThreadingHTTPServer(("127.0.0.1", 0), LocalModel)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix="paos-opencode-context-") as temporary:
            result = check(executable, version, Path(temporary), provider, core)
            print(json.dumps(result, ensure_ascii=False))
    finally:
        provider.shutdown()
        provider.server_close()
