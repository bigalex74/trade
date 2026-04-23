#!/bin/bash
set -u
exec /home/user/run_crypto_hourly_report_once.sh >> /home/user/logs/traders/crypto_hourly_report.log 2>&1
