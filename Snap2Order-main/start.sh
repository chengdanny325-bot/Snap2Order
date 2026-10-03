#!/bin/sh
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
    exec python3 launcher.py "$@"
fi
printf '%s\n' '需要安装 Python 3.11+：https://www.python.org/downloads/'
exit 1
