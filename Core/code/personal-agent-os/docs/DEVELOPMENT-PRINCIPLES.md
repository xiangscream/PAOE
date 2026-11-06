# Core development principles

**Scope:** code in this source checkout. Project work rules belong in the
System AGENTS template; this page explains software implementation boundaries.

## 1. A file has one writer and one reason to exist

A Project registry stores only `{schema, id, root_path, homes,
coordinator_home_id}`. It is a locator, not a task database. A Project Vault
owns business facts; each Home TODO owns the current task list; Mail and Notice
have different file writers. An operation must update the owner, not create a
convenient parallel JSON snapshot.

## 2. Separate pure reading, validation and mutation

A read or `--check` must never repair directories, rewrite invalid state or
silently create missing files. For a writer, validate identities, permissions,
expected SHA-256/revision and source bytes *before* publishing new bytes.
Prefer staging + atomic replace; create-if-absent is not an overwrite.

## 3. Preserve intentional human edits

Do not regenerate an existing ENTRY/TODO/AGENTS merely because a new template
is available. The common AGENTS distributor owns only its marked public block;
project-specific text is not template-owned. A conflict should report what the
operator must review, not force a reset or invent a reconciliation database.

## 4. Keep communication facts distinct

Mail persisted, Notice handled, native reminder accepted, Agent read and Task
completed are separate facts. A transport timeout after submission is an
*unknown result*, not permission to retry and duplicate a wake. Runtime/Contact
identity must come from the explicitly registered target; do not borrow another
Agent's token, session or local Desktop credentials.

## 5. Reuse, do not silently deploy

Core manages filesystem behavior and narrow native adapters, not the Harness's
reasoning loop. Libraries are external; installation locators are pointers,
never embedded method copies. No background polling, status cache, duplicate
member list, login automation or new service is required for a basic task.

## 6. Test the invariant, not an obsolete implementation

Each failure class needs an explicit, ideally synthetic test: missing files,
invalid schema, concurrent edit, unexpected links, duplicate message, uncertain
wake, bad root. The test must prove **no unintended write** as well as the
error code. Run the core verifier and, for actual adoption, verify the native
Windows/WSL runtime with Rooter separately.

## 7. Debugging and readable code

Prefer one purpose-focused module docstring and comments at non-obvious
boundaries (lock, idempotency, cross-platform locator, retries) over narrating
each obvious statement. `CODE-TOUR.md` is the learning map; source docstrings
are the behavioral contract. Update the map when the ownership graph changes.

Never commit real Project materials, private runtime files, tokens, credential
values or machine-local installation data. Removing old code does not authorize
deleting data kept on a user's workstation.
