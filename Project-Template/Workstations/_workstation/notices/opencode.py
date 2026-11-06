"""本工位 OpenCode 唤醒入口：bind / status / wake。"""
import sys
sys.dont_write_bytecode = True
from wake_entry import main

if __name__ == "__main__":
    raise SystemExit(main("opencode"))
