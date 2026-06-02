"""SkaleData drop-in replacement for ``apache-airflow-providers-airbyte``.

The upstream operator only supports OAuth2 client credentials or no-auth.
SkaleData ships managed Airbyte with ``global.auth.enabled=false`` and an
ingress that validates an ``sdk_*`` API key, so neither upstream mode works.

This package re-implements the hook, operator, and trigger with a static
bearer-auth flow. Imports mirror the Airflow provider's layout:

    from skale.providers.airbyte.hooks.airbyte import AirbyteHook
    from skale.providers.airbyte.operators.airbyte import AirbyteTriggerSyncOperator
    from skale.providers.airbyte.triggers.airbyte import AirbyteSyncTrigger
"""
