#!/bin/bash
set -u
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec "${PROJECT_DIR}/run_crypto_hourly_report_once.sh" >> /home/user/logs/traders/crypto_hourly_report.log 2>&1
