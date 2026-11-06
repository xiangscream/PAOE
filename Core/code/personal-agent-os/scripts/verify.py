#!/usr/bin/env python3
"""Run the current Core regression suites in isolated subprocesses.

Learning note: each suite has its own process, current working directory and
module discovery root.  This prevents a successful import in one suite from
masking a missing module in another.  We intentionally do not run the retired
Vault scanner or the absent HTTP Dashboard.
"""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys

CORE=Path(__file__).resolve().parents[1]
PACKAGE=CORE.parents[1]


def run(label,arguments,cwd=PACKAGE):
    print(f'\n=== {label} ===',flush=True)
    env=dict(os.environ,PYTHONIOENCODING='utf-8')
    p=subprocess.run([sys.executable,*arguments],cwd=cwd,env=env,
                     stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
    print(p.stdout,flush=True)
    return p.returncode==0 and 'Ran 0 tests' not in p.stdout


def main():
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    results=[run('Architecture',[str(CORE/'scripts/check_architecture.py')]),
             run('Bootstrap + headless real-file integration',['-m','unittest','discover','-s','tests','-v']),
             run('Core receiver + installation contracts',['-m','unittest','discover','-s','tests','-v'],CORE),
             run('Codex registered Home preparation',['-m','unittest','discover','-s',str(CORE/'scripts/tests'),'-p','test_codex_session_start_guard.py','-v']),
             run('Python syntax',['-m','compileall','-q',str(CORE/'scripts'),str(PACKAGE/'portable.py'),str(PACKAGE/'front')])]
    print('\nPortable verifier: '+('PASS' if all(results) else 'FAIL'))
    print('Scope: synthetic files/localhost; no production Homes, native model or Windows Desktop adoption.')
    return 0 if all(results) else 1


if __name__=='__main__':raise SystemExit(main())
