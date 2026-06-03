"""Default Airflow FAB auth-manager config for SkaleData clusters.

Baked into the image at ``/opt/airflow/webserver_config.py`` so customers
don't need to ship a copy in their own repo.

In production, the SkaleData proxy validates the ``sdk_*`` API key at the
edge — Airflow inside the cluster sees only authorized traffic, so an
internal login screen would just be noise. Locally, the SkaleData CLI
runs Airflow behind your dev port without an outer auth layer, so the
same "no internal login" config gives you a usable UI immediately.

Customers who need a stricter internal auth model can override this by:

1. ``COPY webserver_config.py /opt/airflow/webserver_config.py`` in their
   own Dockerfile (runs after our COPY → wins).
2. Mounting their own file at ``/opt/airflow/webserver_config.py`` in
   docker-compose / Kubernetes (volume mount → wins).

Either path overrides this default without forking the image.
"""

AUTH_ROLE_PUBLIC = "Admin"
