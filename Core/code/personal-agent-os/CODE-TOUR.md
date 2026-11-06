# Core source code tour (learning entry)

This page is a **code map**, not another operating guide. Its only job is to
help a reader follow the actual program. The canonical Agent work instructions
remain in the System Project-Template AGENTS public block.

## The complete request path

```text
CLI arguments                        User-visible response
scripts/paos.py  --------------------------> JSON / text / error code
       |                                      ^
       v                                      |
Validate installation and Project locator   |
paos_installation.py + paos_registry.py     |
       |                                      |
       v                                      |
Resolve Home and verify exact identity      |
paos_home.py + paos_workstation.py          |
       |                                      |
       +--> TODO:  paos_todo.py -------------+
       +--> Mail:  paos_mail.py -------------+
       +--> Notice:paos_notice.py ----------+
       +--> view:  paos_attention_service.py+
       |
       +--> Optional explicit outbound: runtime_injection.py
                                              |
                                              +--> native receiver / CAT
```

The first four steps are *normal local file operations*. They need no local
HTTP Dashboard. The outbound branch needs explicit target Contact and a live
external Runtime, and a successful transport receipt is **not** task completion.

## Read in five short passes

1. **Paths and identity:** `paos_installation.py` and `paos_registry.py`.
   Start with `ProjectRegistry.read_record` versus `register`. Compare it with
   a C++ class that stores a validated path and exposes different read/write
   methods. Observe that a lookup never calls `mkdir`.
2. **The worker's local state:** `paos_home.py`, `paos_workstation.py`, then
   `paos_todo.py`. Search for `parse_todo`, `write_todo` and
   `update_todo_current`. This is a small parser + guarded file transaction,
   not a distributed database. The checkbox is the one task-state field.
3. **Communication:** `paos_mail.py` and `paos_notice.py`. Compare immutable
   Mail (content) and handled Notice (input-processing fact). They intentionally
   do not encode whether the underlying work is done. Handled, read inputs can
   be moved to an explicit external batch by `attention archive-input`; the
   original relative `Workstations/<agent>/...` paths stay usable with
   `attention history-read`. The dispatch envelope stays in place and a replay
   of the same `message_id` reports a missing delivery instead of recreating a
   second Mail or Notice.
4. **Assembly:** `paos_attention_service.py` builds views and composes the
   narrow writers; `paos.py` maps CLI arguments into these calls. Search for
   `build_parser`, then `main`, before reading the middle of its large file.
5. **External execution:** `paos_contact.py`, `paos_wakeup.py`,
   `runtime_injection.py`, `wakeup_native/codex_receiver.py`. Trace STOP,
   caller identity and the uncertain-delivery case. Do not call it in a real
   Desktop session while learning unless explicitly authorized.

## Source modules by responsibility

| Module(s) | Why retained | Important boundary |
| --- | --- | --- |
| `paos.py`, `paos_orient.py` | CLI command dispatch and human-readable current entry | No parallel Project database |
| `paos_installation.py`, `paos_registry.py`, `paos_agent_numbers.py` | Installed paths, minimum Project/member location | Read-only operations do not create files |
| `paos_home.py`, `paos_workstation.py` | Stable Home path and new ENTRY/TODO | Never overwrite handwritten existing files |
| `paos_todo.py`, `paos_write_owner.py` | TODO parsing, writer ownership, lock/fingerprint safety | Only one canonical current task fact |
| `paos_mail.py`, `paos_notice.py` | Immutable Mail and durable Notice | Input handled != task finished |
| `paos_attention_service.py`, `paos_agent_activation.py` | Compose Home, Mail, Notice and explicit activation | Do not invent an execution-state database |
| `paos_library.py`, `paos_guide.py` | Discover independent Workflow/Skill/Tool and support Guide diffs | Does not own the method documents |
| `paos_agents_common.py` | Verify/distribute one marked AGENTS public region | Keep project-specific text verbatim |
| `paos_team_overview.py` | Derive PROJECTS/TEAM overview from Registry and files | Read-derived, not manually duplicated roster |
| `paos_cat_cli.py`, `paos_cat_activation.py`, `paos_external_contact.py` | Explicit CAT/cross-agent communication adapter | No implicit CAT server |
| `paos_contact.py`, `paos_contact_package.py`, `paos_wakeup.py` | Registered native target, STOP, wake handling | Unknown delivery is not a negative receipt |
| `runtime_injection.py`, `codex_receiver_session_start.py` | One explicit native submission and own-session preparation | Never borrow another Home's thread/token |
| `paos_cat_relay_windows.py`, `paos_cat_relay_wsl_client.py` | Explicit Windows/WSL CAT transport | No background poll or automatic fallback |
| `wakeup_native/*.py`, `workbuddy_extension/*.cjs` | Codex/WorkBuddy native transport implementation | Run only in an authorized native environment |
| `paos_backup.py`, `release_check.py` | Deliberate backup and release checks | Restore boundaries and source-only release checks differ |
| `check_architecture.py`, `verify.py` | Test architectural invariants and run isolated suites | Test pass is not production runtime validation |
| `Core/portable.py` | Create initial local config and validate external Library pointers | Never create/copy Libraries or Homes |
| `Core/front/` | Optional read/display UI | CLI survives when the board is off |

## Learning exercises (all use disposable paths)

**A. Inspect the parser.** In a temporary directory, create a TODO via
`render_todo`, parse it with `parse_todo`, change a checkbox, and parse again.
Find which fields changed and which did not. Compare parsing to a C++ lexer:
syntax is recognized first, semantic validation follows.

**B. See optimistic locking.** Run a synthetic `update_todo_current` once
with a correct expected fingerprint, then repeat with the old fingerprint.
The second write must fail without overwriting the intervening content.
Compare this to compare-and-swap (CAS), with file bytes as the expected value.

**C. Separate messaging from work.** Read `send_mail` and `create_notice`.
Find the create-if-absent behavior and the explicit handling flag; note the
absence of any automatic change to TODO task completion.

**D. Follow a failed installation.** Run `portable.py plan`, then test
`portable.py init` with nonexistent external Library roots *only in a copied
source*. Observe that no `config/local` pair is published and no external
library directory is created.

## How the tests are organized

- `Core/tests/`: portable configuration, Project, TODO, board and integrated
  synthetic command tests.
- `source/tests/`: installation and native receiver contracts.
- `source/scripts/tests/`: cross-runtime injection and Contact diagnostics.
- `source/scripts/verify.py`: the orchestrator running these suites in
  independent processes. It does not start any external Runtime.

Use `python code/personal-agent-os/scripts/verify.py` from Core and
`node --test tests/board-ui.test.mjs` for the optional board. Tests run on
synthetic Homes and mocked/local transports, not production credentials.

**Reading rule:** Look at one function's inputs, returned value, mutations and
exception conditions before reading its callers. Comments mark surprising
invariants, not obvious assignments. The program is the authoritative behavior
when a document and source disagree.
