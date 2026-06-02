"""SkaleData bearer-auth hook for managed Airbyte.

Subclass of upstream :class:`airflow.providers.airbyte.hooks.airbyte.AirbyteHook`
that builds the Airbyte SDK with ``Security(bearer_auth=conn.password)``
instead of the OAuth2 client-credentials flow the upstream uses.

Expected Airflow connection (id ``airbyte_default``):

    Conn Type: Airbyte
    Host:     https://<cluster>.skaledata.run/api/public/v1/
    Password: sdk_...  (the SkaleData API key)
"""

from __future__ import annotations

from airbyte_api import AirbyteAPI
from airbyte_api.models import Security
from airflow.providers.airbyte.hooks.airbyte import AirbyteHook as _UpstreamAirbyteHook


class AirbyteHook(_UpstreamAirbyteHook):
    def create_api_session(self) -> AirbyteAPI:
        return AirbyteAPI(
            server_url=self.conn["host"],
            security=Security(bearer_auth=self.conn["client_secret"]),
        )
