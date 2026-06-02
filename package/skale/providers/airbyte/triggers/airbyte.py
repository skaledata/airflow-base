"""SkaleData deferrable trigger for managed Airbyte syncs."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from airbyte_api.models import JobStatusEnum
from airflow.providers.airbyte.triggers.airbyte import (
    AirbyteSyncTrigger as _UpstreamAirbyteSyncTrigger,
)
from airflow.triggers.base import TriggerEvent

from skale.providers.airbyte.hooks.airbyte import AirbyteHook


class AirbyteSyncTrigger(_UpstreamAirbyteSyncTrigger):
    """Drop-in for ``AirbyteSyncTrigger`` that uses SkaleData's bearer-auth hook.

    Overrides ``serialize`` to point at this classpath so the triggerer
    reconstructs the subclass after restart, and ``run`` to swap the hook
    reference. Everything else matches upstream.
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
        hook = AirbyteHook(airbyte_conn_id=self.conn_id)
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
