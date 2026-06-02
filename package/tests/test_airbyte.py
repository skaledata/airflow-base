"""Smoke tests for the Airbyte bearer-auth shim.

These tests verify the shim's *shape* — that the classes exist, subclass the
upstream ones, and override the right methods — without actually talking to
an Airbyte server. Behavior against a live Airbyte happens in the e2e tests
on the SkaleData side, not here.
"""

from __future__ import annotations

from airflow.plugins_manager import AirflowPlugin
from airflow.providers.airbyte.hooks.airbyte import AirbyteHook
from airflow.providers.airbyte.operators.airbyte import AirbyteTriggerSyncOperator
from airflow.providers.airbyte.triggers.airbyte import AirbyteSyncTrigger

from skaledata_airflow_plugins.airbyte import (
    SkaleDataAirbyteHook,
    SkaleDataAirbytePlugin,
    SkaleDataAirbyteSyncTrigger,
    SkaleDataAirbyteTriggerSyncOperator,
)


def test_hook_subclasses_upstream() -> None:
    assert issubclass(SkaleDataAirbyteHook, AirbyteHook)


def test_operator_subclasses_upstream() -> None:
    assert issubclass(SkaleDataAirbyteTriggerSyncOperator, AirbyteTriggerSyncOperator)


def test_trigger_subclasses_upstream() -> None:
    assert issubclass(SkaleDataAirbyteSyncTrigger, AirbyteSyncTrigger)


def test_hook_overrides_create_api_session() -> None:
    # The whole reason this shim exists — we must own create_api_session
    # so the bearer token gets used instead of OAuth2 client credentials.
    assert SkaleDataAirbyteHook.create_api_session is not AirbyteHook.create_api_session


def test_trigger_overrides_serialize_and_run() -> None:
    # serialize must point at our classpath so the triggerer reconstructs the
    # subclass after restart. run must use SkaleDataAirbyteHook.
    assert SkaleDataAirbyteSyncTrigger.serialize is not AirbyteSyncTrigger.serialize
    assert SkaleDataAirbyteSyncTrigger.run is not AirbyteSyncTrigger.run


def test_plugin_registers_hook() -> None:
    assert issubclass(SkaleDataAirbytePlugin, AirflowPlugin)
    assert SkaleDataAirbytePlugin.name == "skaledata_airbyte"
    assert SkaleDataAirbyteHook in SkaleDataAirbytePlugin.hooks
