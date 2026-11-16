"""本工位 DSH 唤醒入口：bind / status / wake（需 Core 支持 dsh 驱动）。"""
import sys
sys.dont_write_bytecode = True
from wake_entry import main

if __name__ == "__main__":
    raise SystemExit(main("dsh"))
