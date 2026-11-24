# Windows content watch

One foreground process observes the selected installation's registered Project
roots (including EXM when registered), Workflow/Skill roots, and the explicitly
registered tool catalog. It writes versions to the existing
`Data/content/events.sqlite3`; it does not invoke models or refresh QMD itself.

## Run the observer

Use the selected installation's normal CLI:

```powershell
paos --installation-file C:/path/installation.json --json content watch
```

The foreground observer reports `subscribed` and `ready` to stderr. Ctrl+C or a Windows
console break requests a coordinated stop. The final JSON result is written to stdout.
A second observer for the same Data directory exits with `content_watch_already_running`.

No extra port, dependency, per-Project process, or production installation change
is needed. Rooter owns login startup and deployment. `watch.lock` uses an OS byte
lock scoped to Data: a second observer for the same installation fails; a dead
process releases the lock automatically. The leftover file is not a stale lock.

## Content boundary

Only the explicit installation descriptor and its registry are read, without
environment-variable fallback to a different Library registration. The exact
Data root is excluded even if it has a different directory name. Workstations,
mailbox, History/archive directories, private-data, hidden directories, virtual
environments, dependency directories, and editor temporary files are excluded.
Junctions and symbolic links within registered roots are not followed. The tool
catalog is a file-only exception in its registered location: nearby Rooter files
are never enumerated or versioned. Scope registrations are fixed for one run;
restart after changing them. Missing configured roots fail startup explicitly.

All remaining ordinary files are eligible originals, including binary assets.
Startup and lost-event recovery read their content to determine versions. Normal
events only read the changed final path (or a newly moved directory subtree),
after 300 ms of quiet. This is not a recurrent full-root hash scan.

## Event and stop contract

- Queue `ReadDirectoryChangesW` on **every** root before startup reconciliation.
  Changes during the scan remain in the OS notification buffers.
- Rearm each overlapped request before processing its previous buffer. A zero-byte
  notification or enumeration-loss error schedules a complete root reconciliation.
- Coalesce events by final path; temporary-save paths are excluded. Atomic replace
  and directory rename are reconciled from the readable final originals. Sharing
  locks and files still changing remain pending. Other read errors fail visibly.
- A disconnected or replaced root stays explicitly disconnected; retry subscription
  once per second. Only after subscribing again reconcile its content. A once-per-
  second root identity check detects replacement of the watched directory itself;
  it does not enumerate content. A permanent disconnect is not reported as healthy.
- Ctrl+C/Ctrl+Break/coordinated stop sets the shared Event. Cancel outstanding I/O,
  wait for completion before releasing buffers, close all handles, then reconcile
  final readable originals and release the instance lock. Disconnected or still-
  changing originals produce `ok:false`. A forced kill has no final flush; the next
  startup scan recovers surviving originals.
- The version/locator unique key is exactly `paos_content.record_version`, shared
  with `stage deliver`. Origin is `watcher`; the existing first-origin field is not
  rewritten when a stage and watcher see the same version.

This observes surviving original versions, not an edit journal. Transient versions
saved and deleted before reconciliation are not recoverable. File removal is not
a new readable original and does not currently publish an index-deletion command;
old version rows stay as source history. QMD deletion propagation is a separate
consumer contract. No production watcher or task scheduler is enabled by tests.

## Verification

```powershell
python -m unittest discover -s Core/tests -p test_content_watch.py -v
python Core/code/personal-agent-os/scripts/verify.py
```

The dedicated tests use actual temporary directories, native Windows notifications,
buffer overflow, directory disconnect/reconnect, editor atomic save and rename,
the real stage writer, public CLI registration, and coordinated shutdown. They
also prove exclusion of Data/Home/history and a real junction to an unregistered
directory. Native tests are explicitly skipped on non-Windows hosts.

Microsoft contracts used: [ReadDirectoryChangesW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-readdirectorychangesw)
and [canceling pending I/O](https://learn.microsoft.com/en-us/windows/win32/fileio/canceling-pending-i-o-operations).
