# skaledata-airflow-plugins

Airflow plugins published by SkaleData. Pre-installed in
[`ghcr.io/skaledata/airflow`](https://github.com/skaledata/airflow-base);
also installable from PyPI for customers running their own Airflow image.

## What's in it

### `SkaleDataAirbyteHook` / `SkaleDataAirbyteTriggerSyncOperator` / `SkaleDataAirbyteSyncTrigger`

Drop-in replacements for the upstream Airbyte provider's hook, operator, and trigger
that authenticate via a static bearer token (the SkaleData `sdk_*` API key) instead of
the upstream OAuth2 `/applications/token` flow.

SkaleData ships its managed Airbyte with `global.auth.enabled: false`. The Caddy ingress
in front of Airbyte validates the API key at the edge, so the standard
`apache-airflow-providers-airbyte` connector — which only supports OAuth2 client
credentials or no-auth — can't talk to it.

## Airflow connection setup

| Field           | Value                                                |
| --------------- | ---------------------------------------------------- |
| Conn Type       | Airbyte                                              |
| Host            | `https://<cluster>.skaledata.run/api/public/v1/`     |
| Password (client secret) | `sdk_...` (your SkaleData API key)          |
| Login / Token URL       | leave blank                                  |

## DAG usage

```python
from skaledata_airflow_plugins.airbyte import SkaleDataAirbyteTriggerSyncOperator

run_sync = SkaleDataAirbyteTriggerSyncOperator(
    task_id="run_airbyte_sync",
    airbyte_conn_id="airbyte_default",
    connection_id="<your-airbyte-connection-id>",
    deferrable=True,
)
```

Everything else (timeouts, async/deferrable modes, etc.) matches the upstream
`AirbyteTriggerSyncOperator` API.
