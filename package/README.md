# airflow-provider-skaledata

SkaleData's Airflow extensions. Pre-installed in
[`ghcr.io/skaledata/airflow`](https://github.com/skaledata/airflow-base) — if
you're using the SkaleData base image you don't need to do anything.

If you're running your own Airflow image:

```bash
pip install airflow-provider-skaledata
```

The PyPI distribution is `airflow-provider-skaledata` (matches the Apache
community-provider naming convention). Imports live under the
`skale.providers.*` namespace.

## Namespace

Mirrors Airflow's own provider layout
(`airflow.providers.<name>.{hooks,operators,triggers}.<name>`) under
`skale.providers.*`:

```python
from skale.providers.airbyte.hooks.airbyte    import AirbyteHook
from skale.providers.airbyte.operators.airbyte import AirbyteTriggerSyncOperator
from skale.providers.airbyte.triggers.airbyte  import AirbyteSyncTrigger
```

Subsequent SkaleData providers (`skale.providers.<other>...`) slot in here.

## What's in it today

### `skale.providers.airbyte` — bearer-auth shim for managed Airbyte

Drop-in replacements for the upstream Airbyte provider's hook, operator, and
trigger that authenticate via a static bearer token (your SkaleData `sdk_*` API
key) instead of the upstream OAuth2 `/applications/token` flow.

SkaleData ships its managed Airbyte with `global.auth.enabled: false`. The Caddy
ingress in front of Airbyte validates the API key at the edge, so the standard
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
from datetime import datetime
from airflow.decorators import dag
from skale.providers.airbyte.operators.airbyte import AirbyteTriggerSyncOperator


@dag(start_date=datetime(2026, 1, 1), schedule=None, catchup=False)
def run_airbyte_sync():
    AirbyteTriggerSyncOperator(
        task_id="sync_postgres_to_warehouse",
        airbyte_conn_id="airbyte_default",
        connection_id="<your-airbyte-connection-uuid>",
        deferrable=True,
    )


run_airbyte_sync()
```

`AirbyteTriggerSyncOperator` is a drop-in for the upstream
`AirbyteTriggerSyncOperator` — same arguments, same async/deferrable semantics.
