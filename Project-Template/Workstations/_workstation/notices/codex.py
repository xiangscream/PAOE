"""本工位 Codex 唤醒器：bind / prepare / status / wake。"""
import sys
sys.dont_write_bytecode = True
from wake_entry import main

if __name__ == "__main__":
    raise SystemExit(main("codex"))
