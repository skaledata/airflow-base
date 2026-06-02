"""SkaleData bearer-auth shim for the Airbyte provider.

SkaleData ships its managed Airbyte with ``global.auth.enabled: false`` in the
helm chart. Its Caddy ingress validates the ``sdk_*`` API key at the edge.
The upstream OAuth2 ``/applications/token`` flow the provider expects doesn't
exist on these clusters, so we route requests through a static bearer.

This module exports three things:

* :class:`SkaleDataAirbyteHook` — subclass of ``AirbyteHook`` that builds the
  SDK with ``Security(bearer_auth=conn.password)``.
* :class:`SkaleDataAirbyteSyncTrigger` — drop-in for ``AirbyteSyncTrigger``
  that uses the hook above. **Required** because deferrable operators
  reconstruct triggers by classpath in the triggerer process; monkey-patching
  the hook reference in the worker doesn't carry over.
* :class:`SkaleDataAirbyteTriggerSyncOperator` — drop-in for
  ``AirbyteTriggerSyncOperator`` that uses both of the above.

Expected Airflow connection (id ``airbyte_default``):
    Conn Type: Airbyte
    Server URL (host):        https://<cluster>.skaledata.run/api/public/v1/
    Client Secret (password): sdk_...  (the SkaleData API key)
    Client ID / Token URL:    leave blank
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from airbyte_api import AirbyteAPI
from airbyte_api.models import JobStatusEnum, Security
from airflow.exceptions import AirflowException
from airflow.plugins_manager import AirflowPlugin
from airflow.providers.airbyte.hooks.airbyte import AirbyteHook
from airflow.providers.airbyte.operators.airbyte import AirbyteTriggerSyncOperator
from airflow.providers.airbyte.triggers.airbyte import AirbyteSyncTrigger
from airflow.triggers.base import TriggerEvent
from airflow.utils.context import Context


class SkaleDataAirbyteHook(AirbyteHook):
    def create_api_session(self) -> AirbyteAPI:
        return AirbyteAPI(
            server_url=self.conn["host"],
            security=Security(bearer_auth=self.conn["client_secret"]),
        )


class SkaleDataAirbyteSyncTrigger(AirbyteSyncTrigger):
    """Mirror of upstream AirbyteSyncTrigger that uses SkaleDataAirbyteHook.

    Overrides ``serialize`` to point at this classpath so the triggerer
    rebuilds the same subclass after restart, and ``run`` to swap the hook
    reference. Everything else is unchanged from upstream.
    """

    def serialize(self) -> tuple[str, dict[str, Any]]:
        return (
            f"{self.__class__.__module__}.{self.__class__.__name__}",
            {
                "job_id": self.job_id,
                "conn_id": self.conn_id,
                "end_time": self.end_time,
                "poll_interval": self.poll_interval,
            },
        )

    async def run(self) -> AsyncIterator[TriggerEvent]:
        hook = SkaleDataAirbyteHook(airbyte_conn_id=self.conn_id)
        try:
            while await self.is_still_running(hook):
                if self.end_time < time.time():
                    msg = (
                        f"Job run {self.job_id} has not reached a terminal status after "
                        f"{self.end_time} seconds."
                    )
                    yield TriggerEvent(
                        {
                            "status": "error",
                            "message": msg,
                            "job_id": self.job_id,
                        }
                    )
                    return
                await asyncio.sleep(self.poll_interval)
            job_run_status = hook.get_job_status(self.job_id)
            if job_run_status == JobStatusEnum.SUCCEEDED:
                yield TriggerEvent(
                    {
                        "status": "success",
                        "message": f"Job run {self.job_id} has completed successfully.",
                        "job_id": self.job_id,
                    }
                )
            elif job_run_status == JobStatusEnum.CANCELLED:
                yield TriggerEvent(
                    {
                        "status": "cancelled",
                        "message": f"Job run {self.job_id} has been cancelled.",
                        "job_id": self.job_id,
                    }
                )
            else:
                yield TriggerEvent(
                    {
                        "status": "error",
                        "message": f"Job run {self.job_id} has failed.",
                        "job_id": self.job_id,
                    }
                )
        except Exception as e:
            yield TriggerEvent({"status": "error", "message": str(e), "job_id": self.job_id})


class SkaleDataAirbyteTriggerSyncOperator(AirbyteTriggerSyncOperator):
    """Mirror of upstream AirbyteTriggerSyncOperator that uses SkaleDataAirbyteHook
    and defers to SkaleDataAirbyteSyncTrigger."""

    def execute(self, context: Context) -> Any:
        hook = SkaleDataAirbyteHook(
            airbyte_conn_id=self.airbyte_conn_id, api_version=self.api_version
        )
        job_object = hook.submit_sync_connection(connection_id=self.connection_id)
        self.job_id = job_object.job_id
        state = job_object.status
        end_time = time.time() + self.timeout

        self.log.info("Job %s was submitted to Airbyte Server", self.job_id)

        if self.asynchronous:
            self.log.info("Async Task returning job_id %s", self.job_id)
            return self.job_id

        if not self.deferrable:
            self.log.debug("Running in non-deferrable mode...")
            hook.wait_for_job(
                job_id=self.job_id, wait_seconds=self.wait_seconds, timeout=self.timeout
            )
        else:
            self.log.debug("Running in deferrable mode in job state %s...", state)
            if state in (JobStatusEnum.RUNNING, JobStatusEnum.PENDING, JobStatusEnum.INCOMPLETE):
                self.defer(
                    timeout=self.execution_timeout,
                    trigger=SkaleDataAirbyteSyncTrigger(
                        conn_id=self.airbyte_conn_id,
                        job_id=self.job_id,
                        end_time=end_time,
                        poll_interval=60,
                    ),
                    method_name="execute_complete",
                )
            elif state == JobStatusEnum.SUCCEEDED:
                self.log.info("Job %s completed successfully", self.job_id)
                return
            elif state == JobStatusEnum.FAILED:
                raise AirflowException(f"Job failed:\n{self.job_id}")
            elif state == JobStatusEnum.CANCELLED:
                raise AirflowException(f"Job was cancelled:\n{self.job_id}")
            else:
                raise AirflowException(
                    f"Encountered unexpected state `{state}` for job_id `{self.job_id}"
                )

        return self.job_id


class SkaleDataAirbytePlugin(AirflowPlugin):
    name = "skaledata_airbyte"
    hooks = [SkaleDataAirbyteHook]
