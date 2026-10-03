"""Usage: python3 backup.py /absolute/path/to/backup.sqlite3"""
import sqlite3
import sys
from pathlib import Path
import server
if len(sys.argv) != 2:
    raise SystemExit('用法：python3 backup.py /备份路径/backup.sqlite3')
target=Path(sys.argv[1]).resolve()
if target.exists():
    raise SystemExit('目标已存在，请换一个备份文件名')
if not server.DB_PATH.exists():
    raise SystemExit('数据库不存在，请先启动服务')
target.parent.mkdir(parents=True,exist_ok=True)
with server.connect() as source,sqlite3.connect(target) as destination:
    source.backup(destination)
print('备份完成：'+str(target))
