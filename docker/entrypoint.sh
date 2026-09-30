#!/bin/sh
# Prepare the log volume, then drop root. The environment, including Fly
# secrets, is kept. This script does not call the network.
set -eu

log_path="${ARGENTINE_LOG_PATH:-/data/gate-log.jsonl}"
data_dir="$(dirname "$log_path")"
mkdir -p "$data_dir"

if [ "$(id -u)" = "0" ] && id gate >/dev/null 2>&1; then
  chown -R gate:gate "$data_dir"
  exec python3 - << 'PY'
import os
import pwd

user = pwd.getpwnam("gate")
os.initgroups(user.pw_name, user.pw_gid)
os.setgid(user.pw_gid)
os.setuid(user.pw_uid)
os.execvp("python3", ["python3", "-m", "argentine", "serve"])
PY
fi

exec python3 -m argentine serve
