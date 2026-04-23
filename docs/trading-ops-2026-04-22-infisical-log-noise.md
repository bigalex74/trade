# Trading Ops: Infisical Log Noise Fix 2026-04-22

## Context

Cron logs were polluted by Infisical CLI service messages:

- update warnings;
- release notices;
- `Injecting N Infisical secrets into your application process`.

The application output itself is still useful and should remain in logs.

## Change

Added `/home/user/run_infisical_quiet.sh`.

The wrapper runs:

```bash
/usr/bin/infisical --silent run "$@"
```

and filters only known Infisical service-noise lines. It preserves the child command output and propagates a non-zero exit status when Infisical or the child command fails.

## Updated Call Sites

- Active crontab Infisical jobs now use `/home/user/run_infisical_quiet.sh`.
- Disabled crontab lines were also normalized so they stay quiet if re-enabled.
- Local helper scripts now use the wrapper:
  - `/home/user/run_moex_collector.sh`
  - `/home/user/n8n-docker/run-n8n.sh`
  - `/home/user/n8n-docker/start-n8n.sh`
  - `/home/user/n8n-docker/scripts/cleanup_test_cron.sh`
  - `/home/user/lightrag-trade/scripts/compose_with_infisical.sh`
  - `/home/user/n8n-docker/scripts/compose_with_infisical.sh`

## Tests

- `bash -n` passed for the wrapper and updated shell scripts.
- Crontab was checked: Infisical cron jobs now route through `/home/user/run_infisical_quiet.sh`.
- Positive smoke test:

```bash
/home/user/run_infisical_quiet.sh --env dev --projectId ... -- /bin/sh -c 'echo app-output'
```

Output contained only `app-output`.

- Failure smoke test:

```bash
/home/user/run_infisical_quiet.sh --env dev --projectId ... -- /bin/sh -c 'echo app-error >&2; exit 7'
```

Output preserved `app-error` and returned non-zero. Infisical reports the child failure as exit code `1`, which is acceptable for cron failure detection.

## Notes

This does not upgrade Infisical. It only prevents Infisical's own update/injection notices from polluting application logs.
