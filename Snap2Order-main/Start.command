#!/bin/bash
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
    python3 launcher.py
else
    echo "需要安装 Python 3.11+：https://www.python.org/downloads/"
fi
read -r -p "按回车关闭窗口…" _snap_exit
