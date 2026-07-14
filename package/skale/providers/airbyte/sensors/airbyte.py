"""SkaleData drop-in sensor for waiting on Airbyte sync jobs.

Pairs with ``AirbyteTriggerSyncOperator(asynchronous=True)``: the operator
returns the job id immediately and this sensor polls it to completion, so a
retry re-checks the existing job instead of submitting a duplicate sync.
"""

from __future__ import annotations

import time
from typing import Any

from airbyte_api.models import JobStatusEnum
from airflow.exceptions import AirflowException
from airflow.providers.airbyte.sensors.airbyte import (
    AirbyteJobSensor as _UpstreamAirbyteJobSensor,
)
from airflow.utils.context import Context

from skale.providers.airbyte.hooks.airbyte import AirbyteHook
from skale.providers.airbyte.triggers.airbyte import AirbyteSyncTrigger


class AirbyteJobSensor(_UpstreamAirbyteJobSensor):
    """Drop-in for upstream ``AirbyteJobSensor`` that uses SkaleData's
    bearer-auth hook and defers to :class:`AirbyteSyncTrigger`."""

    def poke(self, context: Context) -> bool:
        hook = AirbyteHook(airbyte_conn_id=self.airbyte_conn_id, api_version=self.api_version)
        job = hook.get_job_details(job_id=self.airbyte_job_id)
        status = job.status

        if status == JobStatusEnum.FAILED:
            raise AirflowException(f"Job failed: \n{job}")
        elif status == JobStatusEnum.CANCELLED:
            raise AirflowException(f"Job was cancelled: \n{job}")
        elif status == JobStatusEnum.SUCCEEDED:
            self.log.info("Job %s completed successfully.", self.airbyte_job_id)
            return True

        self.log.info("Waiting for job %s to complete.", self.airbyte_job_id)
        return False

    def execute(self, context: Context) -> Any:
        if not self.deferrable:
            return super().execute(context)

        hook = AirbyteHook(airbyte_conn_id=self.airbyte_conn_id, api_version=self.api_version)
        job = hook.get_job_details(job_id=int(self.airbyte_job_id))
        state = job.status
        end_time = time.time() + self.timeout

        self.log.info("Airbyte Job Id: Job %s", self.airbyte_job_id)

        if state in (JobStatusEnum.RUNNING, JobStatusEnum.PENDING, JobStatusEnum.INCOMPLETE):
            self.defer(
                timeout=self.execution_timeout,
                trigger=AirbyteSyncTrigger(
                    conn_id=self.airbyte_conn_id,
                    job_id=self.airbyte_job_id,
                    end_time=end_time,
                    poll_interval=60,
                ),
                method_name="execute_complete",
            )
        elif state == JobStatusEnum.SUCCEEDED:
            self.log.info("%s completed successfully.", self.task_id)
            return
        elif state == JobStatusEnum.FAILED:
            raise AirflowException(f"Job failed:\n{job}")
        elif state == JobStatusEnum.CANCELLED:
            raise AirflowException(f"Job was cancelled:\n{job}")
        else:
            raise AirflowException(
                f"Encountered unexpected state `{state}` for job_id `{self.airbyte_job_id}"
            )
