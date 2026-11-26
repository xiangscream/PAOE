"""One installation's default Windows Codex application connection, without a caller identity."""
import ctypes
import json
import ntpath
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath

from paos_installation import effective_data_root
from wakeup_native.process_identity import process_snapshot, valid_identity


TRANSPORT_ENV = "PAOS_CODEX_TRANSPORT_FILE"
SCHEMA = "paoe-codex-application-transport/v1"


class TransportProblem(ValueError):
    pass


def desktop_scope(environment):
    if os.name != "nt" or environment.get("CODEX_ELECTRON_USER_DATA_PATH", "").strip():
        raise TransportProblem("desktop_transport_profile_unsupported")
    home = Path(environment.get("CODEX_HOME") or Path.home() / ".codex")
    if not home.is_absolute():
        raise TransportProblem("desktop_transport_profile_unsupported")
    return ntpath.normcase(str(home.resolve()))


def pipe_host(pipe):
    """Inspect this supplied pipe's server instance; never enumerate pipes or credentials."""
    from ctypes import wintypes
    import msvcrt

    if not isinstance(pipe, str) or not pipe.startswith("\\\\.\\pipe\\codex-app-tools"):
        raise TransportProblem("desktop_transport_pipe_unsupported")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetNamedPipeServerProcessId.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG))
    kernel.GetNamedPipeServerProcessId.restype = wintypes.BOOL
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD))
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    with open(pipe, "r+b", buffering=0) as stream:
        pid = wintypes.ULONG()
        if not kernel.GetNamedPipeServerProcessId(msvcrt.get_osfhandle(stream.fileno()), ctypes.byref(pid)):
            raise ctypes.WinError(ctypes.get_last_error())
        before = process_snapshot(pid.value)
        handle = kernel.OpenProcess(0x1000, False, pid.value)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            image = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(image))
            if not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel.CloseHandle(handle)
        parts = PureWindowsPath(image.value).parts
        if (len(parts) < 4 or parts[-4].casefold() != "windowsapps"
                or not re.fullmatch(r"OpenAI\.Codex_[0-9.]+_(?:x64|arm64)__2p2nqsd0c76g0", parts[-3])
                or parts[-2:] != ("app", "ChatGPT.exe")):
            raise TransportProblem("desktop_transport_product_unsupported")
        after = process_snapshot(pid.value)
        if (before.get("alive") is not True or after != before
                or not valid_identity(before.get("identity"))):
            raise TransportProblem("desktop_transport_host_unverified")
        return {"pid": pid.value, "process_identity": before["identity"]}


@contextmanager
def _publication_lock(path):
    import msvcrt
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def _read_record(path):
    value = json.loads(Path(path).read_bytes())
    if (not isinstance(value, dict) or value.get("schema") != SCHEMA
            or not isinstance(value.get("scope"), str) or not value["scope"]
            or not isinstance(value.get("pipe"), str) or not value["pipe"]
            or type(value.get("pid")) is not int or value["pid"] <= 0
            or not valid_identity(value.get("process_identity"))
            or not value["process_identity"].startswith("windows:")):
        raise TransportProblem("desktop_transport_record_invalid")
    return value


def publish_current(descriptor, environment):
    """Publish after the native Hook/manual Owner, Home and STOP checks succeed."""
    scope = desktop_scope(environment)
    pipe = environment["CODEX_APP_TOOLS_PIPE_PATH"]
    path = effective_data_root(descriptor) / "runtime-injection" / "codex-desktop" / "transport.json"
    with _publication_lock(path):
        current = pipe_host(pipe)
        if path.exists():
            previous = _read_record(path)
            if previous["scope"] != scope:
                raise TransportProblem("desktop_transport_scope_mismatch")
            if (previous["pid"], previous["process_identity"]) == (current["pid"], current["process_identity"]):
                if previous["pipe"] == pipe:
                    return path
                try:
                    pipe_host(previous["pipe"])
                except FileNotFoundError:
                    pass  # The exact old connection is gone, while the new one belongs to this host.
                else:
                    raise TransportProblem("desktop_transport_ambiguous")
            else:
                old = process_snapshot(previous["pid"])
                if old.get("alive") is None:
                    raise TransportProblem("desktop_transport_host_unverified")
                if old["alive"] and old.get("identity") == previous["process_identity"]:
                    raise TransportProblem("desktop_transport_ambiguous")
        value = {"schema": SCHEMA, "scope": scope, "pipe": pipe, **current}
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".transport-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(value, stream)
                stream.write("\n")
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return path


def current_pipe(path, scope):
    """Select once before a new request; fail explicitly without trying an old connection."""
    value = _read_record(path)
    if value["scope"] != scope:
        raise TransportProblem("desktop_transport_scope_mismatch")
    actual = pipe_host(value["pipe"])
    if actual != {"pid": value["pid"], "process_identity": value["process_identity"]}:
        raise TransportProblem("desktop_transport_host_changed")
    return value["pipe"]
