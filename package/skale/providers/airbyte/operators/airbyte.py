"""SkaleData drop-in operator for triggering Airbyte syncs."""

from __future__ import annotations

import time
from typing import Any

from airbyte_api.models import JobStatusEnum
from airflow.exceptions import AirflowException
from airflow.providers.airbyte.operators.airbyte import (
    AirbyteTriggerSyncOperator as _UpstreamAirbyteTriggerSyncOperator,
)
from airflow.utils.context import Context

from skale.providers.airbyte.hooks.airbyte import AirbyteHook
from skale.providers.airbyte.triggers.airbyte import AirbyteSyncTrigger


class AirbyteTriggerSyncOperator(_UpstreamAirbyteTriggerSyncOperator):
    """Drop-in for upstream ``AirbyteTriggerSyncOperator`` that uses SkaleData's
    bearer-auth hook and defers to :class:`AirbyteSyncTrigger`."""

    def execute(self, context: Context) -> Any:
        hook = AirbyteHook(airbyte_conn_id=self.airbyte_conn_id, api_version=self.api_version)
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
                    trigger=AirbyteSyncTrigger(
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
