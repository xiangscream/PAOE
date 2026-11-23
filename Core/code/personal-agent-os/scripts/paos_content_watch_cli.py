"""Run one scoped observer and drain pending events on a normal stop."""

import argparse
import json
import signal
import sys
from threading import Event

from paos_installation import resolve_installation_path, InstallationProblem
from paos_library import LibraryProblem
from paos_registry import RegistryProblem


def add_watch_parser(content_subparsers):
    return content_subparsers.add_parser("watch", help="Observe registered local originals on Windows")


def execute_watch(args, installation, *, stop=None, emit=None):
    from paos_content_watch import ContentScope, ContentWatcher, WatcherAlreadyRunning

    if emit is None:
        emit = lambda event: print(json.dumps(event, ensure_ascii=False), file=sys.stderr, flush=True)
    previous = {}
    try:
        if stop is None:
            stop = Event()
            signals = [signal.SIGINT, signal.SIGTERM]
            if hasattr(signal, "SIGBREAK"):
                signals.append(signal.SIGBREAK)
            for sig in signals:
                previous[sig] = signal.signal(sig, lambda *_: stop.set())
        return ContentWatcher(ContentScope(installation), emit=emit).run(stop)
    except WatcherAlreadyRunning as error:
        return {"ok": False, "error_code": "content_watch_already_running", "error": str(error)}
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation-file", required=True)
    content = parser.add_subparsers(dest="command", required=True).add_parser("content")
    add_watch_parser(content.add_subparsers(dest="content_command", required=True))
    args = parser.parse_args()
    try:
        result = execute_watch(args, resolve_installation_path(args.installation_file))
    except (OSError, ValueError, RuntimeError, InstallationProblem, LibraryProblem, RegistryProblem) as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
