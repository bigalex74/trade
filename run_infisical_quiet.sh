#!/usr/bin/env bash
set -o pipefail

filter_infisical_noise() {
  sed -u -E \
    -e '/Injecting [0-9]+ Infisical secrets into your application process/d' \
    -e '/^Update Required:/d' \
    -e '/^Please update to the new installation script/d' \
    -e '/^A new release of infisical is available:/d' \
    -e '/^To update, run:/d'
}

/usr/bin/infisical --silent run "$@" 2>&1 | filter_infisical_noise
exit "${PIPESTATUS[0]}"
