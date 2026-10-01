#!/bin/sh
# Prepare the log volume, then drop root. The environment, including platform
# secrets, is kept. This script does not call the network.
#
# Railway injects PORT and health-checks that port. The process reads
# ARGENTINE_PORT. When PORT is set, listen there. Fly does not set PORT;
# the image and fly.toml keep ARGENTINE_PORT=8080 for Fly's proxy.
set -eu

if [ -n "${PORT:-}" ]; then
  case "$PORT" in
    *[!0-9]*)
      echo "PORT must be an integer from 1 to 65535" >&2
      exit 2
      ;;
  esac
  if [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    echo "PORT must be an integer from 1 to 65535" >&2
    exit 2
  fi
  export ARGENTINE_PORT="$PORT"
fi

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
