"""One overlapped directory subscription; no worker thread or filesystem polling."""

import ctypes as c
from ctypes import wintypes as w
import os
import struct


class Overflow(OSError):
    pass


class OVERLAPPED(c.Structure):
    _fields_ = [("Internal", c.c_size_t), ("InternalHigh", c.c_size_t),
                ("Offset", w.DWORD), ("OffsetHigh", w.DWORD), ("hEvent", w.HANDLE)]


def api():
    if os.name != "nt":
        raise OSError("content watch requires Windows")
    dll = c.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateFileW": ([w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE], w.HANDLE),
        "CreateEventW": ([c.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR], w.HANDLE),
        "ReadDirectoryChangesW": ([w.HANDLE, c.c_void_p, w.DWORD, w.BOOL, w.DWORD, c.c_void_p, c.POINTER(OVERLAPPED), c.c_void_p], w.BOOL),
        "GetOverlappedResult": ([w.HANDLE, c.POINTER(OVERLAPPED), c.POINTER(w.DWORD), w.BOOL], w.BOOL),
        "CancelIoEx": ([w.HANDLE, c.POINTER(OVERLAPPED)], w.BOOL),
        "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
        "ResetEvent": ([w.HANDLE], w.BOOL),
        "CloseHandle": ([w.HANDLE], w.BOOL),
    }
    for name, (args, result) in signatures.items():
        fn = getattr(dll, name)
        fn.argtypes, fn.restype = args, result
    return dll


class DirectorySubscription:
    def __init__(self, root, *, buffer_size=64 * 1024, recursive=True):
        self.root = root
        self.recursive = recursive
        self.dll = api()
        self.handle = self.dll.CreateFileW(str(root), 1, 7, None, 3, 0x42000000, None)
        if self.handle == c.c_void_p(-1).value:
            raise c.WinError(c.get_last_error())
        self.event = self.dll.CreateEventW(None, True, False, None)
        if not self.event:
            self.dll.CloseHandle(self.handle)
            raise c.WinError(c.get_last_error())
        self.buffer = c.create_string_buffer(buffer_size)
        self.overlapped = OVERLAPPED(hEvent=self.event)
        self.pending = False
        try:
            self.arm()
        except OSError:
            self.close()
            raise

    def arm(self):
        self.dll.ResetEvent(self.event)
        self.overlapped = OVERLAPPED(hEvent=self.event)
        if not self.dll.ReadDirectoryChangesW(self.handle, self.buffer, len(self.buffer),
                                             self.recursive, 0x1B, None, c.byref(self.overlapped), None):
            error = c.get_last_error()
            if error != 997:  # ERROR_IO_PENDING
                raise c.WinError(error)
        self.pending = True

    def poll(self):
        wait = self.dll.WaitForSingleObject(self.event, 0)
        if wait == 258:
            return []
        if wait != 0:
            raise c.WinError(c.get_last_error())
        size = w.DWORD()
        ok = self.dll.GetOverlappedResult(self.handle, c.byref(self.overlapped), c.byref(size), False)
        error = 0 if ok else c.get_last_error()
        self.pending = False
        if error and error not in (234, 1022):
            raise c.WinError(error)
        payload = self.buffer.raw[:size.value]
        self.arm()  # Keep collecting while the caller reconciles or hashes originals.
        if error or not size.value:
            raise Overflow("directory notifications lost; reconcile required")
        names, offset = [], 0
        while True:
            advance, action, length = struct.unpack_from("<III", payload, offset)
            name = payload[offset + 12:offset + 12 + length].decode("utf-16-le")
            names.append(self.root / name)
            if not advance:
                break
            offset += advance
        return names

    def close(self):
        if self.handle is None:
            return
        try:
            if self.pending:
                # Cancellation is a request. Keep buffer/OVERLAPPED alive until completion.
                if not self.dll.CancelIoEx(self.handle, c.byref(self.overlapped)):
                    error = c.get_last_error()
                    if error != 1168:  # already completed
                        raise c.WinError(error)
                size = w.DWORD()
                if not self.dll.GetOverlappedResult(self.handle, c.byref(self.overlapped), c.byref(size), True):
                    error = c.get_last_error()
                    if error not in (995, 1022, 234):
                        raise c.WinError(error)
        finally:
            self.dll.CloseHandle(self.handle)
            self.dll.CloseHandle(self.event)
            self.handle = None
            self.pending = False
