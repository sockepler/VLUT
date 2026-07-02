#!/bin/bash
# gm/id 设计工具启动脚本
cd "$(dirname "$0")"
export GMID_PORT=${GMID_PORT:-8650}
echo "gm/id 工具启动: http://localhost:$GMID_PORT  (linux02: http://192.168.0.126:$GMID_PORT)"
exec ./venv/bin/python -m gmid.app
