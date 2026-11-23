"""Installation-scoped Windows content observer, sharing stage-delivery versions."""

from contextlib import contextmanager
from pathlib import Path
import os
import time

from paos_content import changes_db, original_version, record_version
from paos_installation import effective_data_root, load_installation_descriptor
from paos_library import load_library_roots
from paos_registry import ProjectRegistry
from paos_workstation import posix_windows_drive_locator
from paos_content_watch_win32 import DirectorySubscription, Overflow


EXCLUDED = frozenset({"data", "workstations", "mailbox", "history", "archive", "archives",
                      "private-data", "node_modules", "__pycache__", ".git", ".obsidian",
                      ".paos", ".venv", "venv"})
TEMP_SUFFIXES = (".tmp", ".temp", ".swp", ".swo", "~")


def local(raw):
    return Path(posix_windows_drive_locator(str(raw))).expanduser().resolve()


class ContentScope:
    def __init__(self, installation):
        descriptor = load_installation_descriptor(Path(installation))
        self.data = effective_data_root(descriptor).resolve()
        registry = ProjectRegistry(Path(installation))
        self.roots = set()
        for item in sorted((self.data / "project-registry/projects").glob("*.json")):
            self.roots.add(local(registry.read_record(item.stem)["root_path"]))
        libraries = load_library_roots(local(descriptor["library_roots_config"]), validate_roots=False)
        if libraries["registered"]:
            self.roots.update(local(libraries[k]) for k in ("workflow_root", "skill_root"))
        self.files = {local(libraries["tool_catalog"])} if libraries.get("tool_catalog") else set()
        self.blocked = [self.data]
        if descriptor.get("rooter_home"):
            self.blocked.append(local(descriptor["rooter_home"]))
        for root in self.roots:
            if not root.is_dir() or any(root.is_relative_to(b) for b in self.blocked):
                raise ValueError(f"Invalid business content root: {root}")
        # Tool catalog is an explicitly registered original, not its surrounding Home.
        for file in self.files:
            if not file.is_file() or file.is_relative_to(self.data):
                raise ValueError(f"Invalid registered tool catalog: {file}")
        self.watch_roots = sorted(self.roots | {f.parent for f in self.files})
        self.watch_roots = [r for r in self.watch_roots
                            if not any(r != other and r.is_relative_to(other) for other in self.watch_roots)]
        if not self.watch_roots:
            raise ValueError("No registered content roots")

    def allows(self, path):
        path = Path(path).absolute()
        if path.is_relative_to(self.data):
            return False
        if path in self.files:
            return not path.is_symlink()
        if any(path.is_relative_to(b) for b in self.blocked):
            return False
        for root in self.roots:
            if path.is_relative_to(root):
                parts = path.relative_to(root).parts
                if any(p.casefold() in EXCLUDED or p.startswith(".") for p in parts):
                    return False
                if path.name.casefold().endswith(TEMP_SUFFIXES):
                    return False
                # Never follow a junction/symlink out of the registered originals.
                for candidate in (path, *path.parents):
                    if candidate == root:
                        break
                    try:
                        attributes = candidate.lstat()
                    except FileNotFoundError:
                        continue
                    if candidate.is_symlink() or getattr(attributes, "st_file_attributes", 0) & 0x400:
                        return False
                return True
        return False

    def originals(self, selected):
        selected = Path(selected)
        if selected.is_file():
            if self.allows(selected):
                yield selected.resolve()
            return
        # A file-only tool catalog subscription must not walk its containing Home.
        if selected not in self.roots and not self.allows(selected):
            for file in self.files:
                if file.is_relative_to(selected) and file.is_file():
                    yield file
            return
        def fail(error):
            raise error
        for directory, dirs, files in os.walk(selected, onerror=fail, followlinks=False):
            base = Path(directory)
            dirs[:] = [d for d in dirs if self.allows(base / d)]
            for name in files:
                file = base / name
                if self.allows(file):
                    yield file.resolve()


@contextmanager
def single_watcher(data):
    import msvcrt
    path = data / "content/watch.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock:
        if path.stat().st_size == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError("content watch already owns this installation") from exc
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


class ContentWatcher:
    def __init__(self, scope, *, subscription=DirectorySubscription, emit=lambda event: None,
                 settle_seconds=0.3):
        self.scope, self.subscription, self.emit = scope, subscription, emit
        self.settle_seconds = settle_seconds
        self.streams, self.pending, self.retry_at = {}, {}, {}
        self.identities = {}
        self.next_health = 0.0

    def reconcile(self, paths):
        seen = set()
        for selected in paths:
            try:
                for file in self.scope.originals(selected):
                    if file in seen:
                        continue
                    seen.add(file)
                    try:
                        before = file.stat()
                        version = original_version(file)
                        after = file.stat()
                    except FileNotFoundError:
                        continue  # Atomic replacement/removal; final path event follows.
                    except OSError as exc:
                        if getattr(exc, "winerror", None) not in (32, 33):
                            raise
                        self.pending[file] = time.monotonic() + self.settle_seconds
                        continue  # Editor holds a sharing lock; keep the original pending.
                    if (before.st_mtime_ns, before.st_size, before.st_ino) != (after.st_mtime_ns, after.st_size, after.st_ino):
                        self.pending[file] = time.monotonic() + self.settle_seconds
                        continue
                    with changes_db(self.scope.data) as db:
                        record_version(db, str(file), version, "original", "watcher")
            except FileNotFoundError:
                continue  # Removed directory; any replacement is subscribed already.

    def connect(self, root):
        identity = root.stat().st_ino
        self.streams[root] = self.subscription(root)
        self.identities[root] = identity

    def start(self):
        started = False
        try:
            for root in self.scope.watch_roots:
                self.connect(root)
            self.emit({"event": "subscribed", "roots": [str(r) for r in self.streams]})
            self.reconcile(self.scope.watch_roots)
            self.emit({"event": "ready"})
            started = True
        finally:
            if not started:
                self.close()

    def disconnected(self, root, error, now):
        stream = self.streams.pop(root)
        stream.close()
        self.retry_at[root] = now + 1
        self.emit({"event": "disconnected", "root": str(root), "error": str(error)})

    def step(self):
        now = time.monotonic()
        for root, stream in list(self.streams.items()):
            try:
                for path in stream.poll():
                    if self.scope.allows(path):
                        self.pending[path] = now + self.settle_seconds
                if now >= self.next_health and root.stat().st_ino != self.identities[root]:
                    raise OSError("Registered directory was replaced")
            except Overflow:
                self.pending[root] = now
                self.emit({"event": "overflow", "root": str(root)})
            except OSError as exc:
                self.disconnected(root, exc, now)
        if now >= self.next_health:
            self.next_health = now + 1
        for root, due in list(self.retry_at.items()):
            if now < due:
                continue
            try:
                self.connect(root)
            except OSError:
                self.retry_at[root] = now + 1
                continue  # Disconnected status remains visible until actual re-subscription.
            del self.retry_at[root]
            self.pending[root] = now
            self.emit({"event": "reconnected", "root": str(root)})
        due = [p for p, deadline in self.pending.items() if deadline <= now]
        for path in due:
            del self.pending[path]
        self.reconcile(due)

    def close(self):
        errors = []
        for stream in self.streams.values():
            try:
                stream.close()
            except OSError as exc:
                errors.append(str(exc))
        self.streams.clear()
        if errors:
            raise OSError("; ".join(errors))

    def run(self, stop):
        with single_watcher(self.scope.data):
            self.start()
            try:
                while not stop.wait(0.05):
                    self.step()
            finally:
                self.close()
            # After native I/O has completed, record final readable originals.
            # Later changes belong to the next startup reconciliation.
            self.pending.clear()
            self.reconcile(self.scope.watch_roots)
            result = {"ok": not self.retry_at and not self.pending,
                      "event": "stopped", "disconnected": [str(r) for r in self.retry_at],
                      "unsettled": [str(p) for p in self.pending]}
            self.emit(result)
            return result
