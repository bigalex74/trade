#!/bin/bash
set -u

exec /usr/sbin/logrotate \
  -s /home/user/logs/.logrotate.status \
  /home/user/logrotate-trading.conf
