#!/bin/bash
set -u

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

exec /usr/sbin/logrotate \
  -s /home/user/logs/.logrotate.status \
  "${PROJECT_DIR}/logrotate-trading.conf"
