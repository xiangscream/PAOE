"""Inject one reminder into a configured native Runtime; no business state or retries.

Python: inject(target, message, model=None)
CLI stdin: {"target": {...}, "message": "...", "model": optional_native_model}
"""
from __future__ import annotations

import argparse
import base64
import errno
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from contextlib import contextmanager
from http.client import HTTPException
from pathlib import Path, PureWindowsPath
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from urllib.error import HTTPError, URLError

from paos_workstation import posix_windows_drive_locator
from paos_installation import InstallationProblem, load_installation_descriptor, resolve_installation_path
from wakeup_native.codex_app_tools import (
    CodexCallerOutOfProcessTree,
    CodexDesktop,
    CodexTargetPipeRuntime,
)
from wakeup_native.diagnostics import exception_fields, transport_fields
from wakeup_native.process_identity import valid_identity


class InjectionError(RuntimeError):
    """A native target cannot accept this reminder now."""

    def __init__(self, message, *, code="native_rejected", state="native_rejected",
                 repair_owner="target_owner", next_action="原Owner核本人入口；不换路或自动重发。", diagnostic=None):
        super().__init__(message)
        self.code = code
        self.state = state
        self.repair_owner = repair_owner
        self.next_action = next_action
        self.diagnostic = transport_fields(diagnostic)

    def details(self):
        return {"error_code": self.code, "state": self.state, "repair_owner": self.repair_owner,
                "next_action": self.next_action, "retry": False,
                **({"diagnostic": self.diagnostic} if self.diagnostic else {})}


class InjectionUncertain(InjectionError):
    """The one call may have reached Windows; no confirmed receipt, no resend."""

    def __init__(self, message, *, diagnostic=None):
        super().__init__(message, code="delivery_not_confirmed", state="delivery_uncertain",
                         next_action="保留原业务和回执；交原Owner核实，不重发或换路。", diagnostic=diagnostic)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _check_stop(target):
    if target.get("stop_file") and Path(posix_windows_drive_locator(target["stop_file"])).exists():
        raise InjectionError("Explicit STOP prevents native injection", code="native_stopped", state="native_stopped",
                             next_action="尊重原STOP；只有原授权主体可解除，不自动重投。")


@contextmanager
def _native_lock(target):
    # OS locks release on process exit. The empty file is not an attempt record.
    origin = "" if target["runtime"] == "codex" else target.get("base_url", "")
    key = json.dumps([target["runtime"], origin, target["session_id"]])
    path = Path.home() / ".paos" / "runtime-injection" / "locks" / hashlib.sha256(key.encode()).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            if path.stat().st_size == 0:
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            acquire = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(stream, fcntl.LOCK_UN)
        try:
            acquire()
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
            raise InjectionError("Another native injection is in progress") from exc
        try:
            yield
        finally:
            stream.seek(0)
            release()


def _request(target, origin, method, path, payload=None, token=None, *, request_id=None, authorization=None):
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    if authorization is not None:
        headers["Authorization"] = authorization
    if request_id is not None:
        headers["X-PAOS-Request-ID"] = request_id
    request = Request(origin + path, data=data, headers=headers, method=method)
    # Do not forward authorization or prompts through redirects/system proxies.
    with build_opener(ProxyHandler({}), NoRedirect()).open(
        request, timeout=float(target.get("timeout_seconds", 30))
    ) as response:
        body = response.read()
        return (json.loads(body.decode("utf-8")) if body else None), response.status


def _origin(value):
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("base_url must be an HTTP(S) origin")
    return value.rstrip("/")


def _codex_extension_send(target, message, model):
    """Sender side for the exact-code receiver entry.

    The authenticated target entry proves its own OS instance identity; the
    caller reads only the grant locator and token. No caller-side process query
    is required, so Windows sandbox/ACL differences cannot turn a valid target
    entry into a false rejection. A target that cannot prove its identity is
    still a definite no-send, never a fallback transport or a resend.
    """
    ext = target.get("extension")
    ext = ext if isinstance(ext, dict) else {}
    runtime_file = str(ext.get("receiver_runtime_file") or "").strip()
    descriptor = None
    expected_identity = None
    if runtime_file:
        path = Path(posix_windows_drive_locator(runtime_file))
        foreign_process_host = (
            os.name != "nt" and (
                re.match(r"^[A-Za-z]:[\\/]", runtime_file)
                or str(path).startswith("/mnt/")
                or runtime_file.startswith("\\\\")
            )
        )
        if foreign_process_host:
            raise InjectionError("Receiver process host is not confirmed in this caller environment",
                                 code="receiver_host_unconfirmed", state="caller_environment_unavailable",
                                 repair_owner="caller_installation_owner",
                                 next_action="Configure the explicit Windows execution entry; do not guess the host or switch routes.")
        try:
            descriptor = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise InjectionError(f"Codex receiver runtime file missing/unreadable at {path}: {exc}",
                                 code="receiver_runtime_unreadable", state="receiver_not_prepared") from exc
        except (UnicodeError, ValueError) as exc:
            raise InjectionError(f"Codex receiver runtime file invalid at {path}: {exc}",
                                 code="receiver_runtime_invalid", state="receiver_not_prepared") from exc
        if not isinstance(descriptor, dict):
            raise InjectionError("Codex receiver runtime file must be a JSON object")
        if str(descriptor.get("schema") or "") != "paos-codex-self-reminder/v1":
            raise InjectionError("Codex receiver runtime file schema must be paos-codex-self-reminder/v1")
        granted = str(descriptor.get("session_id") or "")
        if granted != target["session_id"]:
            raise InjectionError("Codex receiver grant does not match this target session")
        expected_identity = descriptor.get("process_identity")
        if not valid_identity(expected_identity):
            raise InjectionError(
                "Codex receiver grant does not publish a verifiable OS instance identity",
                code="receiver_identity_unverified", state="receiver_not_prepared",
                next_action="Target owner must prepare a receiver that publishes process_identity; caller OS query is not a fallback.",
            )
        endpoint = str(descriptor.get("endpoint") or "")
        token = str(descriptor.get("token") or "")
    else:
        endpoint = str(ext.get("endpoint") or "")
        token = str(ext.get("token") or "")
    if not endpoint or not token:
        raise InjectionError(
            "Codex target-side extension is configured without endpoint/token"
        )
    origin = _origin(endpoint)
    parsed = urlsplit(origin)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
        raise InjectionError("Codex target-side extension must be a 127.0.0.1 loopback origin")
    _check_stop(target)
    request_id = uuid.uuid4().hex
    if runtime_file:
        status_diagnostic = {"request_id": request_id, "phase": "status_read"}
        try:
            receiver, status = _request(target, origin, "GET", "/status", token=token,
                                        request_id=request_id)
        except HTTPError as exc:
            status_diagnostic.update(exception_fields(exc), http_status=exc.code)
            exc.close()
            code = "receiver_status_rejected" if exc.code in {401, 403} else "receiver_status_unavailable"
            raise InjectionError(
                "Codex receiver status request was rejected; no reminder submitted",
                code=code, state="receiver_not_prepared",
                next_action="Target owner must check the grant and the receiver's /status identity entry; do not resend or reroute.",
                diagnostic=status_diagnostic,
            ) from exc
        except (URLError, OSError) as exc:
            reason = exc.reason if isinstance(exc, URLError) else exc
            status_diagnostic.update(exception_fields(exc))
            if isinstance(reason, ConnectionRefusedError) or (
                    isinstance(reason, OSError) and reason.errno == errno.ECONNREFUSED):
                raise InjectionError(
                    "Codex receiver connection refused; no reminder delivered",
                    code="receiver_connection_refused", state="receiver_offline",
                    diagnostic=status_diagnostic,
                ) from exc
            raise InjectionError(
                "Codex receiver status unavailable; no reminder submitted",
                code="receiver_status_unavailable", state="receiver_not_prepared",
                next_action="Target owner must restore the authenticated /status identity entry; do not resend or reroute.",
                diagnostic=status_diagnostic,
            ) from exc
        except (HTTPException, ValueError, UnicodeError) as exc:
            status_diagnostic.update(exception_fields(exc))
            raise InjectionError(
                "Codex receiver status response unreadable; no reminder submitted",
                code="receiver_status_unavailable", state="receiver_not_prepared",
                next_action="Target owner must restore the authenticated /status identity entry; do not resend or reroute.",
                diagnostic=status_diagnostic,
            ) from exc
        if (status != 200 or not isinstance(receiver, dict)
                or receiver.get("session_id") != target["session_id"]):
            raise InjectionError(
                "Codex receiver status identity is not confirmed; no reminder submitted",
                code="receiver_status_unavailable", state="receiver_not_prepared",
                next_action="Target owner must restore the authenticated /status identity entry; do not resend or reroute.",
                diagnostic=status_diagnostic,
            )
        actual_identity = receiver.get("process_identity")
        if not valid_identity(actual_identity):
            raise InjectionError(
                "Codex receiver status does not publish a verifiable OS instance identity; no reminder submitted",
                code="receiver_identity_unverified", state="receiver_not_prepared",
                next_action="Target owner must normal prepare the receiver; do not resend or reroute.",
                diagnostic=status_diagnostic,
            )
        if actual_identity != expected_identity:
            status_diagnostic["reason"] = "receiver_identity_mismatch"
            raise InjectionError(
                "Codex receiver status belongs to a different process instance; no reminder submitted",
                code="receiver_identity_mismatch", state="receiver_offline",
                next_action="Target owner must normal prepare the registered receiver; do not resend or reroute.",
                diagnostic=status_diagnostic,
            )
        _check_stop(target)
    payload = {
        "session_id": target["session_id"],
        "message": message,
    }
    diagnostic = {"request_id": request_id, "phase": "http_wait"}
    try:
        result, status = _request(target, origin, "POST", "/send", payload, token=token, request_id=request_id)
    except HTTPError as exc:
        diagnostic.update(exception_fields(exc), http_status=exc.code)
        if exc.code in {400, 401, 403, 404, 409, 502, 503}:
            try:
                body = json.loads(exc.read().decode("utf-8"))
            except (OSError, UnicodeError, ValueError):
                body = {}
            code = body.get("error") if isinstance(body, dict) else None
            code = code if isinstance(code, str) else "receiver_rejected"
            remote = transport_fields(body.get("diagnostic")) if isinstance(body, dict) else {}
            # A remote request ID must not replace this call's correlation ID.
            remote.pop("request_id", None)
            remote.pop("http_status", None)
            diagnostic.update(remote)
            if exc.code == 502:
                raise InjectionUncertain("Codex receiver delivery_not_confirmed (HTTP 502); do not resend",
                                         diagnostic=diagnostic) from exc
            states = {"native_busy": "native_busy", "native_stopped": "native_stopped",
                      "native_unreachable": "native_unavailable", "native_unavailable": "native_unavailable"}
            raise InjectionError(f"Codex receiver rejected (HTTP {exc.code})",
                                 code=code,
                                 state=states.get(code, "native_rejected"), diagnostic=diagnostic) from exc
        raise InjectionUncertain(f"Codex receiver HTTP {exc.code} delivery not confirmed; do not resend", diagnostic=diagnostic) from exc
    except (URLError, OSError) as exc:
        reason = exc.reason if isinstance(exc, URLError) else exc
        diagnostic.update(exception_fields(exc))
        if isinstance(reason, ConnectionRefusedError) or (isinstance(reason, OSError) and reason.errno == errno.ECONNREFUSED):
            raise InjectionError("Codex receiver connection refused; no reminder delivered",
                                 code="receiver_connection_refused", state="receiver_offline", diagnostic=diagnostic) from exc
        raise InjectionUncertain("Codex receiver response not confirmed; do not resend", diagnostic=diagnostic) from exc
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise InjectionUncertain("Codex receiver response unreadable; do not resend",
                                 diagnostic={**diagnostic, **exception_fields(exc)}) from exc
    if status != 200 or not isinstance(result, dict) or result.get("session_id") != target["session_id"]:
        raise InjectionUncertain("Codex receiver send receipt identity not confirmed; do not resend", diagnostic=diagnostic)
    if runtime_file:
        receipt_identity = result.get("process_identity")
        if not valid_identity(receipt_identity) or receipt_identity != expected_identity:
            raise InjectionUncertain(
                "Codex receiver send receipt instance identity not confirmed; do not resend",
                diagnostic={**diagnostic, "reason": "receiver_identity_mismatch"},
            )
    if result.get("accepted") is not True:
        raise InjectionUncertain("Codex receiver send receipt acceptance not confirmed; do not resend", diagnostic=diagnostic)
    bridge = result.get("bridge_result")
    return {
        "native_disposition": bridge.get("disposition") if isinstance(bridge, dict) else None,
        "via": "target_extension",
        "accepted": True,
        "request_id": request_id,
        "native_status_before_submit": result.get("native_status_before_submit"),
    }


def _codex(target, message, model):
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ValueError("Codex model must be a nonempty native model name")
    ext = target.get("extension")
    ext = ext if isinstance(ext, dict) else {}
    if str(ext.get("receiver_runtime_file") or "").strip():
        # 显式 receiver_runtime_file 是唯一选路：与调用方是否自带 Codex 环境
        # 无关，先于 locate 选定；失败即结构化返回，不再尝试另一发送路径。
        return _codex_extension_send(target, message, model)
    try:
        client, status = CodexDesktop().locate(target["session_id"])
    except CodexCallerOutOfProcessTree as exc:
        raise InjectionError(
            "Codex caller is outside the Codex Desktop process tree and no "
            "target-side extension is configured", code="receiver_not_registered", state="receiver_not_prepared"
        ) from exc
    except CodexTargetPipeRuntime as exc:
        raise InjectionError(f"Codex target pipe unreachable: {exc}") from exc
    except (OSError, EOFError, RuntimeError, json.JSONDecodeError, UnicodeError) as exc:
        # locate only reads status. No reminder has crossed the send boundary.
        raise InjectionError(
            f"Codex Desktop preflight unavailable ({type(exc).__name__}); no reminder submitted",
            code="codex_preflight_failed", state="native_unavailable",
            next_action="原Owner从当前Desktop正常prepare接收入口；原邮件保留，不自动重发。",
            diagnostic={"phase": "status_read", **exception_fields(exc)},
        ) from exc
    if status == "active":
        raise InjectionError(
            "Codex target is active; no reminder injected",
            code="native_busy", state="native_busy",
            next_action="目标正在工作；保留已投递邮件，由原Owner接续，不自动重发。",
        )
    if status not in {"idle", "notLoaded"}:
        raise InjectionError(f"Codex target is not wakeable: {status}")
    _check_stop(target)
    try:
        client.wake(target["session_id"], message, model=model)
    except (OSError, EOFError, RuntimeError, json.JSONDecodeError, UnicodeError) as exc:
        raise InjectionUncertain(
            f"Codex Desktop send receipt unavailable ({type(exc).__name__}); do not resend",
            diagnostic={"phase": "native_submit", **exception_fields(exc)},
        ) from exc
    return {}


def _windows_native(target, message, model, *, receiver_status=False):
    """One WSL->Windows process handoff, selected before any native send."""
    extension = target["extension"]
    python = str(extension.get("windows_python") or "")
    if not PureWindowsPath(python).is_absolute() or not python.lower().endswith(".exe"):
        raise ValueError("extension.windows_python must name an absolute Windows Python .exe")
    try:
        installation = load_installation_descriptor(resolve_installation_path())
    except InstallationProblem as exc:
        raise InjectionError(f"Windows installation unavailable: {exc}") from exc
    source = str(installation.get("source_root") or "")
    if not installation.get("configured") or not PureWindowsPath(source).is_absolute():
        raise InjectionError("Windows execution requires a registered Windows Source installation")
    argv = [posix_windows_drive_locator(python), "-X", "utf8", "-B",
            str(PureWindowsPath(source) / "scripts" / "runtime_injection.py")]
    # Transfer configured target locators, never caller credentials.
    child_target = {"runtime": target["runtime"], "session_id": target["session_id"],
                    "extension": {"execution_environment": "windows"}}
    if target["runtime"] == "codex":
        child_target["extension"]["receiver_runtime_file"] = extension["receiver_runtime_file"]
    else:
        for field in ("api_version", "base_url", "auth_file"):
            child_target[field] = target[field]
    for field in ("stop_file", "timeout_seconds"):
        if field in target:
            child_target[field] = target[field]
    request = {"target": child_target, "receiver_status": True} if receiver_status else {"target": child_target, "message": message}
    if model is not None:
        request["model"] = model
    try:
        result = subprocess.run(argv, input=json.dumps(request, ensure_ascii=False).encode("utf-8"),
                                capture_output=True, timeout=float(target.get("timeout_seconds", 30)) + 5)
    except subprocess.TimeoutExpired as exc:
        raise InjectionUncertain("Windows receipt not confirmed after timeout; do not resend") from exc
    except OSError as exc:
        raise InjectionError(f"Windows execution unavailable ({type(exc).__name__}); no alternate route",
                             code="windows_execution_unavailable", state="caller_environment_unavailable",
                             repair_owner="caller_installation_owner") from exc
    try:
        receipt = json.loads(result.stdout.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise InjectionUncertain("Windows receipt unreadable; do not resend") from exc
    if receiver_status:
        if (result.returncode != 0 or not isinstance(receipt, dict) or not isinstance(receipt.get("receiver"), dict)
                or receipt.get("session_id") != target["session_id"]):
            raise InjectionError("Windows receiver status not confirmed", code="receiver_status_unknown")
        return receipt["receiver"]
    if isinstance(receipt, dict) and receipt.get("uncertain") is True:
        raise InjectionUncertain("Windows native delivery not confirmed; do not resend", diagnostic=receipt.get("diagnostic"))
    if isinstance(receipt, dict) and receipt.get("accepted") is False and result.returncode != 0:
        raise InjectionError(str(receipt.get("error") or "Windows native injection rejected; do not resend"),
                             code=receipt.get("error_code", "native_rejected"),
                             state=receipt.get("state", "native_rejected"),
                             repair_owner=receipt.get("repair_owner", "target_owner"),
                             next_action=receipt.get("next_action", "原Owner核本人入口；不换路或自动重发。"),
                             diagnostic=receipt.get("diagnostic"))
    if (result.returncode != 0 or not isinstance(receipt, dict) or receipt.get("accepted") is not True
          or receipt.get("runtime") != target["runtime"] or receipt.get("session_id") != target["session_id"]):
        raise InjectionUncertain("Windows receipt identity/acceptance not confirmed; do not resend")
    return {**receipt, "execution_environment": "windows"}


def _opencode(target, message, model):
    version = target.get("api_version", 1)
    if version == 2:
        return _opencode_v2(target, message, model)
    if version != 1:
        raise ValueError("OpenCode api_version must be 1 or 2; no automatic API switching")
    if model is not None and (not isinstance(model, dict) or not all(isinstance(model.get(k), str) and model[k].strip() for k in ("providerID", "modelID"))):
        raise ValueError("OpenCode model requires native providerID and modelID")
    origin = _origin(target["base_url"])
    session_path = "/session/" + quote(target["session_id"], safe="")
    session, status = _request(target, origin, "GET", session_path)
    if status != 200 or not isinstance(session, dict) or session.get("id") != target["session_id"] or not isinstance(session.get("directory"), str) or not session["directory"].strip():
        raise InjectionError("OpenCode exact session/directory could not be resolved")
    query = "?" + urlencode({"directory": session["directory"]})
    states, status = _request(target, origin, "GET", "/session/status" + query)
    if status != 200 or not isinstance(states, dict):
        raise InjectionError("OpenCode native status is unavailable")
    # OpenCode v1.18.33 native admission: prompt 先写 user，loop 复用同一 run
    # handle（SessionRunState.ensureRunning；effect/runner Running/ShellThenRun
    # 同 handle，after-shell 继续原 runner）。busy 新输入经同一 prompt_async
    # 入口进入原 Session，由原生串行接续；PAOS 不再 hard-reject 非 idle，也
    # 不因 busy 丢弃。section-only：STEP native lock 仍是同一提交锁；具体
    # session/directory 精确校验在上方未变；STOP 仍在下方拒绝。状态回执
    # （receipt native_state）只描述受理时的原生状态，不寻找缓存/队列。
    native = states.get(target["session_id"], {"type": "idle"})
    if not isinstance(native, dict) or not isinstance(native.get("type"), str) or not native.get("type").strip():
        raise InjectionError("OpenCode native status is unrecognizable; no reminder injected")
    payload = {"parts": [{"type": "text", "text": message}]}
    if model is not None:
        payload["model"] = model
    _check_stop(target)
    _, status = _request(target, origin, "POST", session_path + "/prompt_async" + query, payload)
    if status != 204:
        raise InjectionError(f"OpenCode prompt_async was not accepted (HTTP {status})")
    return {"http_status": status, "native_state": native["type"]}


def _opencode_v2(target, message, model):
    # 2.0.32 admits plain text and inherits the session model; model changes are
    # a separate persistent operation, not an option on this one-shot reminder.
    if model is not None:
        raise ValueError("OpenCode v2 reminders inherit the session model; configure its model separately")
    credentials = json.loads(Path(posix_windows_drive_locator(target["auth_file"])).read_text(encoding="utf-8-sig"))
    password = credentials["password"]
    if not isinstance(password, str) or not password:
        raise ValueError("OpenCode auth_file requires a nonempty server password")
    authorization = "Basic " + base64.b64encode(("opencode:" + password).encode("utf-8")).decode("ascii")
    origin = _origin(target["base_url"])
    session_path = "/api/session/" + quote(target["session_id"], safe="")
    try:
        response, status = _request(target, origin, "GET", session_path, authorization=authorization)
        session = response.get("data") if isinstance(response, dict) else None
        directory = session.get("location", {}).get("directory") if isinstance(session, dict) else None
        if status != 200 or not isinstance(session, dict) or session.get("id") != target["session_id"] or not isinstance(directory, str) or not directory.strip():
            raise InjectionError("OpenCode v2 exact session/location could not be resolved")
        response, status = _request(target, origin, "GET", "/api/session/active", authorization=authorization)
        states = response.get("data") if isinstance(response, dict) else None
        if status != 200 or not isinstance(states, dict):
            raise InjectionError("OpenCode v2 active-session snapshot is unavailable")
        native = states.get(target["session_id"], {"type": "idle"})
        if not isinstance(native, dict) or native.get("type") not in {"running", "idle"}:
            raise InjectionError("OpenCode v2 active-session state is unrecognizable")
    except (HTTPError, URLError, OSError, ValueError, HTTPException) as exc:
        diagnostic = {"phase": "status_read", **exception_fields(exc)}
        reason = exc.reason if isinstance(exc, URLError) else exc
        if isinstance(reason, ConnectionRefusedError) or (isinstance(reason, OSError) and reason.errno == errno.ECONNREFUSED):
            raise InjectionError("OpenCode v2 preflight connection refused; no reminder delivered",
                                 code="receiver_connection_refused", state="receiver_offline",
                                 diagnostic=diagnostic) from exc
        if isinstance(exc, HTTPError):
            diagnostic["http_status"] = exc.code
            exc.close()
        raise InjectionError("OpenCode v2 session/status preflight failed; no reminder submitted",
                             code="opencode_preflight_failed", diagnostic=diagnostic) from exc
    request_id = uuid.uuid4().hex
    message_id = "msg_" + request_id
    _check_stop(target)
    diagnostic = {"request_id": request_id, "phase": "http_wait"}
    try:
        response, status = _request(target, origin, "POST", session_path + "/prompt",
                                    {"id": message_id, "text": message}, authorization=authorization)
    except HTTPError as exc:
        diagnostic.update(exception_fields(exc), http_status=exc.code)
        exc.close()
        if exc.code in {400, 401, 403, 404}:
            raise InjectionError(f"OpenCode v2 rejected reminder (HTTP {exc.code})",
                                 code="opencode_rejected", diagnostic=diagnostic) from exc
        raise InjectionUncertain(f"OpenCode v2 HTTP {exc.code}; delivery not confirmed, do not resend",
                                 diagnostic=diagnostic) from exc
    except (URLError, OSError, ValueError, HTTPException) as exc:
        reason = exc.reason if isinstance(exc, URLError) else exc
        if isinstance(reason, ConnectionRefusedError) or (isinstance(reason, OSError) and reason.errno == errno.ECONNREFUSED):
            raise InjectionError("OpenCode v2 connection refused; no reminder delivered",
                                 code="receiver_connection_refused", state="receiver_offline",
                                 diagnostic={**diagnostic, **exception_fields(exc)}) from exc
        raise InjectionUncertain("OpenCode v2 receipt not confirmed; do not resend",
                                 diagnostic={**diagnostic, **exception_fields(exc)}) from exc
    item = response.get("data") if isinstance(response, dict) else None
    if (status != 200 or not isinstance(item, dict) or item.get("id") != message_id
            or item.get("sessionID") != target["session_id"] or item.get("type") != "user"
            or item.get("delivery") not in {"steer", "queue"}):
        raise InjectionUncertain("OpenCode v2 receipt identity/admission not confirmed; do not resend",
                                 diagnostic=diagnostic)
    return {"api_version": 2, "http_status": status, "native_state": native["type"],
            "message_id": message_id, "native_disposition": item["delivery"]}


def _workbuddy(target, message, model):
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ValueError("WorkBuddy model must be a nonempty native model name")
    return _extension_reminder(target, message, model, "WorkBuddy")


def _antigravity(target, message, model):
    if model is not None:
        raise ValueError("Antigravity reminders use the registered conversation's model")
    try:
        return _extension_reminder(target, message, None, "Antigravity")
    except FileNotFoundError as exc:
        raise InjectionError(
            "Antigravity Sidecar has no receiver registration",
            code="antigravity_receiver_missing",
            state="receiver_offline",
            next_action="Open Antigravity with the Owner's Sidecar enabled; the durable Mail can also be read directly.",
        ) from exc


def _extension_reminder(target, message, model, product):
    """Send once to a host extension with an explicit local conversation grant."""
    runtime = json.loads(Path(posix_windows_drive_locator(target["runtime_file"])).read_text(encoding="utf-8"))
    if target["session_id"] not in runtime["targets"]:
        raise InjectionError(f"{product} target is outside the extension grant")
    origin = _origin(runtime["endpoint"])
    parsed = urlsplit(origin)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port or not runtime["token"]:
        raise InjectionError(f"{product} requires its authorized loopback extension")
    request_id = uuid.uuid4().hex
    payload = {"session_id": target["session_id"], "message": message, "clientRequestId": request_id}
    if model is not None:
        payload["modelId"] = model
    _check_stop(target)
    diagnostic = {"request_id": request_id, "phase": "http_wait"}
    try:
        result, status = _request(target, origin, "POST", "/send", payload, runtime["token"])
    except HTTPError as exc:
        diagnostic.update(exception_fields(exc), http_status=exc.code)
        exc.close()
        if exc.code in {400, 401, 404}:  # The extension rejects these before native submission.
            raise InjectionError(f"{product} receiver rejected (HTTP {exc.code})",
                                 code="receiver_rejected", diagnostic=diagnostic) from exc
        raise InjectionUncertain(f"{product} receiver HTTP {exc.code} delivery not confirmed; do not resend",
                                 diagnostic=diagnostic) from exc
    except (URLError, OSError) as exc:
        reason = exc.reason if isinstance(exc, URLError) else exc
        diagnostic.update(exception_fields(exc))
        if isinstance(reason, ConnectionRefusedError) or (isinstance(reason, OSError) and reason.errno == errno.ECONNREFUSED):
            raise InjectionError(f"{product} receiver connection refused; no reminder delivered",
                                 code="receiver_connection_refused", state="receiver_offline", diagnostic=diagnostic) from exc
        raise InjectionUncertain(f"{product} receiver response not confirmed; do not resend", diagnostic=diagnostic) from exc
    except (HTTPException, json.JSONDecodeError, UnicodeError) as exc:
        raise InjectionUncertain(f"{product} receiver response unreadable; do not resend",
                                 diagnostic={**diagnostic, **exception_fields(exc)}) from exc
    if status != 200 or not isinstance(result, dict) or result.get("session_id") != target["session_id"] or result.get("clientRequestId") != request_id:
        raise InjectionUncertain(f"{product} native send receipt identity not confirmed; do not resend", diagnostic=diagnostic)
    bridge = result.get("bridge_result")
    return {"request_id": request_id, "native_disposition": bridge.get("disposition") if isinstance(bridge, dict) else None}


DSH_RECEIVER_SCHEMA = "dsh-wake-receiver/v1"
DSH_MODES = frozenset({"queue", "steer"})


def _dsh_config(target):
    """Read the receiver discovery and owner-only secret without exposing either."""
    raw = target.get("receiver_file")
    if not isinstance(raw, str) or not raw.strip():
        raise InjectionError(
            "dsh target requires receiver_file", code="dsh_receiver_config_missing",
            state="receiver_not_prepared",
            next_action="原Owner核 DSH 接收器发现文件与私有 secret；保留原会话/STOP，不重发。",
        )
    path = Path(posix_windows_drive_locator(raw.strip())).expanduser()
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InjectionError(
            "dsh receiver record is missing", code="dsh_receiver_missing",
            state="receiver_offline",
            next_action="启动 DSH 并确认 wake-receiver 已加载；保留原会话/STOP，不重发。",
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise InjectionError(
            "dsh receiver record is unreadable", code="dsh_receiver_unreadable",
            state="receiver_not_prepared",
        ) from exc
    except ValueError as exc:
        raise InjectionError(
            "dsh receiver record is invalid JSON", code="dsh_receiver_invalid",
            state="receiver_not_prepared",
        ) from exc
    if not isinstance(record, dict) or record.get("schema") != DSH_RECEIVER_SCHEMA:
        raise InjectionError(
            "dsh receiver record has an unsupported schema", code="dsh_receiver_invalid",
            state="receiver_not_prepared",
        )
    url = record.get("url")
    secret_file = record.get("secretFile")
    if not isinstance(url, str) or not url.strip() or not isinstance(secret_file, str) or not secret_file.strip():
        raise InjectionError(
            "dsh receiver record is missing url or secretFile", code="dsh_receiver_invalid",
            state="receiver_not_prepared",
        )
    try:
        origin = _origin(url)
    except ValueError as exc:
        raise InjectionError(
            "dsh receiver url must be an HTTP(S) origin", code="dsh_receiver_invalid",
            state="receiver_not_prepared",
        ) from exc
    parsed = urlsplit(origin)
    try:
        port = parsed.port
    except ValueError as exc:
        raise InjectionError(
            "dsh receiver url has an invalid port", code="dsh_receiver_invalid",
            state="receiver_not_prepared",
        ) from exc
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not port:
        raise InjectionError(
            "dsh receiver must be a 127.0.0.1 loopback origin", code="dsh_receiver_invalid",
            state="receiver_not_prepared",
        )
    secret_path = Path(posix_windows_drive_locator(secret_file.strip())).expanduser()
    try:
        secret = secret_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise InjectionError(
            "dsh receiver secret is unreadable", code="dsh_secret_unreadable",
            state="receiver_not_prepared",
            next_action="由原Owner恢复 DSH 私有 secret；不得把它写入 Contact 或命令参数。",
        ) from exc
    if len(secret) < 32:
        raise InjectionError(
            "dsh receiver secret is too short", code="dsh_secret_invalid",
            state="receiver_not_prepared",
        )
    return origin, secret


def _dsh(target, message, model):
    """Submit one prompt to the DSH receiver; acceptance is not consumption."""
    # A DSH wake inherits the target Session's current model. A one-shot model
    # override would silently change a persistent user choice, so reject it.
    if model is not None:
        raise ValueError("dsh 驱动按目标会话当前模型执行，不接受显式 model。")
    mode = target.get("mode", "queue")
    if not isinstance(mode, str) or mode not in DSH_MODES:
        raise ValueError("dsh mode must be queue or steer")
    origin, secret = _dsh_config(target)
    _check_stop(target)
    request_id = uuid.uuid4().hex
    payload = {
        "sessionId": target["session_id"],
        "text": message,
        "mode": mode,
        "requestId": request_id,
    }
    diagnostic = {"request_id": request_id, "phase": "http_wait"}
    try:
        result, status = _request(
            target, origin, "POST", "/wake", payload,
            authorization="Bearer " + secret, request_id=request_id,
        )
    except HTTPError as exc:
        body = {}
        try:
            raw = exc.read()
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (OSError, UnicodeError, ValueError):
            body = {}
        finally:
            exc.close()
        remote = body if isinstance(body, dict) else {}
        diagnostic.update(
            exception_fields(exc), http_status=exc.code,
            remote_code=remote.get("code") if isinstance(remote.get("code"), str) else None,
            remote_retry=remote.get("retry") if isinstance(remote.get("retry"), bool) else None,
            remote_reason=remote.get("reason") if isinstance(remote.get("reason"), str) else None,
        )
        if exc.code == 409:
            raise InjectionError(
                "dsh target Session is busy; no reminder admitted", code="native_busy",
                state="native_busy",
                next_action="目标正在执行；保留原信，由原Owner接续，不自动重发。",
                diagnostic=diagnostic,
            ) from exc
        if exc.code in {401, 403}:
            raise InjectionError(
                "dsh receiver rejected the owner secret", code="dsh_unauthorized",
                state="native_rejected",
                next_action="原Owner核 DSH 私有 secret 与接收器；不重发或换路。",
                diagnostic=diagnostic,
            ) from exc
        if exc.code == 404:
            raise InjectionError(
                "dsh target Session was not found", code="dsh_session_not_found",
                state="native_rejected",
                next_action="核固定的 DSH Session ID 与工作目录；不自动新建或重发。",
                diagnostic=diagnostic,
            ) from exc
        if exc.code == 503:
            raise InjectionError(
                "dsh receiver is not ready", code="dsh_unavailable",
                state="native_unavailable",
                next_action="原Owner恢复 DSH Session controller；保留原信，不重发。",
                diagnostic=diagnostic,
            ) from exc
        if 400 <= exc.code < 500:
            raise InjectionError(
                f"dsh receiver rejected the reminder (HTTP {exc.code})",
                code="dsh_rejected", state="native_rejected",
                diagnostic=diagnostic,
            ) from exc
        # A 5xx can arrive after the controller admitted the prompt. The caller
        # cannot prove whether it was consumed, so preserve unknown and do not
        # resend under a fresh request ID.
        raise InjectionUncertain(
            f"dsh receiver HTTP {exc.code}; delivery not confirmed, do not resend",
            diagnostic=diagnostic,
        ) from exc
    except (URLError, TimeoutError, OSError, HTTPException, ValueError, UnicodeError) as exc:
        reason = exc.reason if isinstance(exc, URLError) else exc
        diagnostic.update(exception_fields(exc))
        if isinstance(reason, ConnectionRefusedError) or (
                isinstance(reason, OSError) and reason.errno == errno.ECONNREFUSED):
            raise InjectionError(
                "dsh receiver connection refused; no reminder delivered",
                code="receiver_connection_refused", state="receiver_offline",
                diagnostic=diagnostic,
            ) from exc
        raise InjectionUncertain(
            "dsh delivery result unknown; do not resend",
            diagnostic=diagnostic,
        ) from exc
    if status != 200 or not isinstance(result, dict):
        raise InjectionUncertain(
            "dsh receipt is unreadable or has the wrong status; do not resend",
            diagnostic={**diagnostic, "http_status": status},
        )
    if result.get("accepted") is False:
        raise InjectionError(
            "dsh receiver did not accept the reminder", code="dsh_rejected",
            state="native_rejected",
            diagnostic={**diagnostic, "http_status": status,
                        "remote_code": result.get("code") if isinstance(result.get("code"), str) else None},
        )
    if (result.get("accepted") is not True or result.get("ok") is not True
            or result.get("sessionId") != target["session_id"]
            or result.get("requestId") != request_id
            or result.get("mode") != mode):
        raise InjectionUncertain(
            "dsh receipt identity was not confirmed; do not resend",
            diagnostic={**diagnostic, "http_status": status,
                        "reason": "receipt_identity_mismatch"},
        )
    return {
        "http_status": status,
        "request_id": result["requestId"],
        "native_disposition": result["mode"],
    }


def inject(target, message, *, model=None):
    """Return native acceptance or raise; never persist/observe business status.

    The dangerous edge is *after* submission but *before* confirmation. A
    timeout can mean the message arrived, so the caller must surface an
    uncertain receipt rather than fall back or retry automatically.
    """
    if not isinstance(target, dict):
        raise ValueError("target must be configured native contact information")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message must be nonempty text")
    if not isinstance(target.get("session_id"), str) or not target["session_id"].strip():
        raise ValueError("session_id must be an explicit native target")
    runtime = target["runtime"]
    functions = {"codex": _codex, "opencode": _opencode, "workbuddy": _workbuddy,
                 "antigravity": _antigravity, "dsh": _dsh}
    if runtime not in functions:
        raise ValueError(f"Unsupported native Runtime: {runtime}")
    extension = target.get("extension") or {}
    execution = extension.get("execution_environment", "local") if isinstance(extension, dict) else "local"
    if execution not in {"local", "windows"}:
        raise ValueError("extension.execution_environment must be local or windows")
    if execution == "windows":
        if runtime == "codex":
            locator = extension.get("receiver_runtime_file")
        elif runtime == "opencode" and target.get("api_version") == 2:
            locator = target.get("auth_file")
        else:
            raise ValueError("Windows execution requires a Codex receiver or OpenCode v2 auth_file")
        if not locator or not PureWindowsPath(str(locator)).is_absolute():
            raise ValueError("Windows execution requires an absolute Windows target locator")
    _check_stop(target)
    if execution == "windows" and os.name != "nt":
        # Windows child takes the existing Windows native lock and STOP gate.
        # Never try WSL HTTP first, and never route again after a failure.
        return _windows_native(target, message, model)
    if runtime == "workbuddy":
        receipt = _workbuddy(target, message, model)
    else:
        with _native_lock(target):
            receipt = functions[runtime](target, message, model)
    result = {"accepted": True, "runtime": runtime, "session_id": target["session_id"], **receipt}
    if execution == "windows":
        result["execution_environment"] = "windows"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        request = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
        if request.get("receiver_status") is True:
            from paos_contact import _codex_receiver_view
            result = {"receiver": _codex_receiver_view(request["target"]), "session_id": request["target"]["session_id"]}
        else:
            result = inject(request["target"], request["message"], model=request.get("model"))
    except (OSError, ValueError, KeyError, RuntimeError, EOFError, URLError) as exc:
        error = {"accepted": False, "error": str(exc)}
        if isinstance(exc, InjectionUncertain):
            error.update(exc.details(), accepted=None, uncertain=True, retry=False)
        elif isinstance(exc, InjectionError):
            error.update(exc.details())
        print(json.dumps(error))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
