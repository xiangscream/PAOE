# PAOE Core source

This source tree implements file-backed Project/Home operations and explicit
communication adapters. Core is not the canonical home of Agent work rules or
professional Workflow/Skill/Tool documents.

```sh
python scripts/paos.py --help
python scripts/verify.py
```

The CLI is an argument dispatcher. For deeper code, begin with
[CODE-TOUR.md](CODE-TOUR.md), then follow the import chain from `paos.py` to
`paos_registry.py`, `paos_workstation.py`, `paos_todo.py`, `paos_mail.py` and
`paos_notice.py`. Native wake has a separate receiver and uncertainty contract.

The installation chooses external Library roots explicitly. Common work rules
are edited in `System/Project-Template/AGENTS.md` and applied to actual Project
AGENTS; advanced operations live in System/Guide. If this source is checked out
outside a System installation, those files must be supplied by that installation.

工位 ENTRY 的正文直接读取所属 System 的
`Project-Template/Workstations/_workstation/ENTRY.md`；独立源码使用
`workstation init --entry-template <母本文件>` 明确提供。
Core 只展开数据字段并保护已有文件，不维护第二份入口文案。
关联检查使用 `scripts/paos_template_check.py --help`；实际检查范围和调用方式
由 System 的 Project-Template/README 维护。

See [development principles](docs/DEVELOPMENT-PRINCIPLES.md) and
[source-only AGENTS](AGENTS.md) before changing writers. Hard communication
references are kept in [runtime injection](docs/RUNTIME-INJECTION.md) and
[Codex self-reminder](docs/CODEX-SELF-REMINDER.md); for runtime behavior, the
currently checked-out code and tests remain decisive.
