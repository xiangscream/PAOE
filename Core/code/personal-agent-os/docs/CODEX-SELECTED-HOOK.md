# Select native sessions, not their shared directory

This increment adds session-selected handlers alongside the reviewed `9a8e13c` adapter.
The session IDs are arguments of the generated hook definitions; no Home or
personal thread ID is built into shared code. It does not install itself.

## Routing

| Native event | Selected session | Other registered or unregistered session |
| --- | --- | --- |
| startup/resume | Unchanged original handler prepares; one appended reader reads context without preparing | Unchanged original handler once |
| UserPromptSubmit | Unchanged original handler prepares; one appended reader reads context without preparing | Unchanged original handler once |
| compact | One new adapter invocation | Empty result; no installation/context/receiver access |
| Stop | One new adapter invocation, existing STOP and turn dedup unchanged | Empty result; no PAOE stop action |

All existing definitions and their event/group/handler positions are preserved,
including both original preparation commands and unrelated Stop hooks. Only new
groups are appended. Before the appended definitions are trusted, the host can
continue running the exact original trusted definitions for every session. After
review, selected startup/resume/request use the original preparation; the appended
adapter performs only one context read. Its delegation message does not assert
that the independently scheduled preparation has completed successfully. compact
still performs its own preparation because the original matcher excludes it.
The selected adapter uses a
30-second handler budget, full context for reading events, and the existing
adapter's explicit-error/STOP/owner checks.

## Prepare a reviewable installation packet

Run from the selected code checkout using actual absolute paths:

```powershell
python scripts/paos_codex_hook_install.py prepare --hooks-file C:/Users/USER/.codex/hooks.json --packet D:/review/codex-selected --session EXACT-THREAD-ID --installation-file D:/review/installation.selected.json --cat-url http://127.0.0.1:8870
```

`--session` is repeatable. `--cat-url` is optional. The selected installation must
point at the reviewed code and current machine data layout. `prepare` reads the
hook file and writes a **new** packet directory only: `original.json` preserves
exact bytes, `candidate.json` is the full replacement, and `plan.json` identifies
the target, selection and executable location. It does not alter live hooks.

Supported original contract: one synchronous `SessionStart` handler with matcher
`^(startup|resume)$`, and one synchronous `UserPromptSubmit` handler, each executing
`"PYTHON" -X utf8 -B ".../codex_receiver_session_start.py"`. Missing, duplicate,
modified or already-new PAOE registrations fail explicitly. Existing sibling
config.toml inline PAOE registrations are checked at prepare and apply; trust-only
records are not registrations. Other plugin/project/managed sources remain visible
in the host hook browser: Rooter must check those for duplicate registrations.

## Rooter applies or restores

```powershell
python scripts/paos_codex_hook_install.py apply --packet D:/review/codex-selected
python scripts/paos_codex_hook_install.py restore --packet D:/review/codex-selected
```

Apply verifies the append-only candidate against its recorded inputs and current original
bytes, then atomically replaces the hook file. Restore requires the live file to
equal that candidate and restores the original bytes exactly. Concurrent/manual
changes produce a conflict, never a force overwrite. Review those changes and
prepare a new packet instead. Retain the packet and fixed checkout for recovery.
Restore does not depend on the selected installation still being present.

These commands never edit `config.toml`, trust hashes, model settings, STOP,
Contact or native processes. Only the appended selected handlers
must be reviewed through the supported native `/hooks` interface or equivalent
supported host UI; an applied file is not proof the hooks are trusted or running.
The original definitions are never changed or moved, including during the review
window and after exact restoration. No trust bypass is used.

## Evidence and limits

`python -m unittest discover -s Core/tests -p test_codex_selected_hook.py -v`
tests pre-review/post-review/restored configurations through real subprocesses for
selected, S052 example and unregistered sessions. The pre-review test selects only
the unchanged definitions at their original positions, modelling the documented
host rule that unreviewed definitions are skipped; it is not a live trust-UI test.
It checks one prepare per selected reading event (old three plus new compact),
one appended context read, one Stop action, unchanged old output, STOP/owner
guards, full-byte restoration, unrelated fields, and conflict refusal. The
original 13 adapter tests remain separate.

Natural host dispatch/trust, model receipt of full context and actual receiver
mail consumption require the original selected session after Rooter's installation.
Isolated input replay proves routing and adapter behavior, not those host outcomes.
No directory-based selection or artificial restart is required.

Official host contracts: [Hook source merging, review and trust](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks).
