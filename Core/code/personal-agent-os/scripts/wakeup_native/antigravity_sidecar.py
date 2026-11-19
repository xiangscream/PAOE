"""Run one registered PAOE reminder endpoint inside an Antigravity App Sidecar."""
from __future__ import annotations

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
from tempfile import NamedTemporaryFile


def agentapi_command(locator):
    """Use the native executable behind the App's Windows batch launcher."""
    path = Path(locator)
    if path.suffix.lower() == ".bat":
        launcher = path.read_text(encoding="utf-8-sig").strip()
        match = re.fullmatch(r'@echo off\n"([^"\r\n]+)" agentapi %\*', launcher, flags=re.IGNORECASE)
        executable = Path(match[1]) if match else None
        if executable and executable.is_absolute() and executable.name.lower() == "language_server.exe" and executable.is_file():
            return [str(executable), "agentapi"]
        raise ValueError("Unrecognized Antigravity Windows agentapi launcher.")
    if os.name == "nt" and path.suffix.lower() != ".exe":
        raise ValueError("Use the App's native agentapi executable or Windows batch launcher.")
    return [str(path)]


def make_server(conversation_id, stop_file, command, token):
    """Bind only loopback; the App-provided agentapi owns the native session."""
    authorization = f"Bearer {token}".encode("ascii")

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, data):
            body = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/send":
                return self.reply(404, {"error": "unknown_route"})
            presented = self.headers.get("Authorization", "").encode("latin-1")
            if not hmac.compare_digest(authorization, presented):
                return self.reply(401, {"error": "invalid_receiver_token"})
            try:
                length = int(self.headers["Content-Length"])
                payload = json.loads(self.rfile.read(length)) if length > 0 else None
            except (TypeError, ValueError):
                return self.reply(400, {"error": "invalid_request"})
            if not isinstance(payload, dict) or payload.get("session_id") != conversation_id:
                return self.reply(404, {"error": "conversation_outside_grant"})
            message = payload.get("message")
            request_id = payload.get("clientRequestId")
            if (not isinstance(message, str) or not message.strip()
                    or not isinstance(request_id, str) or not request_id
                    or "modelId" in payload):
                return self.reply(400, {"error": "invalid_request"})
            if stop_file.exists():
                return self.reply(400, {"error": "native_stopped"})
            try:
                result = subprocess.run(
                    [*command, "send-message", conversation_id, message],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=20, check=False,
                )
            except FileNotFoundError:
                return self.reply(404, {"error": "agentapi_unavailable"})
            except subprocess.TimeoutExpired:
                return self.reply(503, {"error": "agentapi_result_unknown"})
            if result.returncode:
                return self.reply(503, {"error": "agentapi_result_unknown", "exit_code": result.returncode})
            return self.reply(200, {"session_id": conversation_id, "clientRequestId": request_id})

    return HTTPServer(("127.0.0.1", 0), Handler)


def serve(conversation_id, stop_file):
    data_locator = os.environ.get("ANTIGRAVITY_EXECUTABLE_DATA_DIR")
    agentapi = shutil.which("agentapi")
    if not data_locator or not agentapi:
        raise SystemExit("Antigravity must launch this Sidecar with its own agentapi.")
    try:
        command = agentapi_command(agentapi)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    data_dir = Path(data_locator)
    token = secrets.token_urlsafe(32)
    with make_server(conversation_id, stop_file, command, token) as server:
        runtime_file = data_dir / "wake-receiver.json"
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=data_dir, delete=False) as stream:
            staged = Path(stream.name)
            json.dump({
                "endpoint": f"http://127.0.0.1:{server.server_port}",
                "targets": [conversation_id],
                "token": token,
            }, stream)
        try:
            staged.replace(runtime_file)
        finally:
            staged.unlink(missing_ok=True)
        server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conversation", required=True)
    parser.add_argument("--stop-file", required=True, type=Path)
    args = parser.parse_args()
    if not args.conversation.strip() or not args.stop_file.is_absolute():
        parser.error("An explicit conversation ID and absolute STOP path are required.")
    serve(args.conversation, args.stop_file)


if __name__ == "__main__":
    main()
