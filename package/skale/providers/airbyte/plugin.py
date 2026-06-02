"""Airflow plugin registration for the SkaleData Airbyte provider."""

from __future__ import annotations

from airflow.plugins_manager import AirflowPlugin

from skale.providers.airbyte.hooks.airbyte import AirbyteHook


class AirbytePlugin(AirflowPlugin):
    name = "skale_airbyte"
    hooks = [AirbyteHook]
