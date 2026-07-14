"""Smoke tests for the SkaleData Airbyte provider drop-ins.

Verify the classes exist under the documented import paths, subclass the
upstream Airflow provider's classes, and override the right methods.
Behavior against a live Airbyte happens in the e2e tests on the
SkaleData side, not here.
"""

from __future__ import annotations

from airflow.plugins_manager import AirflowPlugin
from airflow.providers.airbyte.hooks.airbyte import AirbyteHook as UpstreamAirbyteHook
from airflow.providers.airbyte.operators.airbyte import (
    AirbyteTriggerSyncOperator as UpstreamAirbyteTriggerSyncOperator,
)
from airflow.providers.airbyte.sensors.airbyte import (
    AirbyteJobSensor as UpstreamAirbyteJobSensor,
)
from airflow.providers.airbyte.triggers.airbyte import (
    AirbyteSyncTrigger as UpstreamAirbyteSyncTrigger,
)

from skale.providers.airbyte.hooks.airbyte import AirbyteHook
from skale.providers.airbyte.operators.airbyte import AirbyteTriggerSyncOperator
from skale.providers.airbyte.plugin import AirbytePlugin
from skale.providers.airbyte.sensors.airbyte import AirbyteJobSensor
from skale.providers.airbyte.triggers.airbyte import AirbyteSyncTrigger


def test_hook_subclasses_upstream() -> None:
    assert issubclass(AirbyteHook, UpstreamAirbyteHook)


def test_operator_subclasses_upstream() -> None:
    assert issubclass(AirbyteTriggerSyncOperator, UpstreamAirbyteTriggerSyncOperator)


def test_trigger_subclasses_upstream() -> None:
    assert issubclass(AirbyteSyncTrigger, UpstreamAirbyteSyncTrigger)


def test_hook_overrides_create_api_session() -> None:
    # The whole reason this hook exists — we own create_api_session
    # so the bearer token gets used instead of OAuth2 client credentials.
    assert AirbyteHook.create_api_session is not UpstreamAirbyteHook.create_api_session


def test_sensor_subclasses_upstream() -> None:
    assert issubclass(AirbyteJobSensor, UpstreamAirbyteJobSensor)


def test_sensor_overrides_poke_and_execute() -> None:
    # Upstream hardcodes its own hook in poke/execute (and its own trigger in
    # the deferrable execute path), so both must be overridden for the
    # bearer-auth hook to be used.
    assert AirbyteJobSensor.poke is not UpstreamAirbyteJobSensor.poke
    assert AirbyteJobSensor.execute is not UpstreamAirbyteJobSensor.execute


def test_trigger_overrides_serialize_and_run() -> None:
    # serialize must point at our classpath so the triggerer reconstructs the
    # subclass after restart. run must use the SkaleData AirbyteHook.
    assert AirbyteSyncTrigger.serialize is not UpstreamAirbyteSyncTrigger.serialize
    assert AirbyteSyncTrigger.run is not UpstreamAirbyteSyncTrigger.run


def test_plugin_registers_hook() -> None:
    assert issubclass(AirbytePlugin, AirflowPlugin)
    assert AirbytePlugin.name == "skale_airbyte"
    assert AirbyteHook in AirbytePlugin.hooks


def test_class_names_match_upstream() -> None:
    # The whole point of the rename: drop the SkaleData prefix because the
    # namespace makes ownership clear. Names must match upstream exactly
    # so that customer DAGs can substitute the import path and be done.
    assert AirbyteHook.__name__ == "AirbyteHook"
    assert AirbyteTriggerSyncOperator.__name__ == "AirbyteTriggerSyncOperator"
    assert AirbyteSyncTrigger.__name__ == "AirbyteSyncTrigger"
    assert AirbyteJobSensor.__name__ == "AirbyteJobSensor"
