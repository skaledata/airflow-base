ARG AIRFLOW_VERSION=3.2.2
ARG PYTHON_VERSION=3.12

FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}

# Re-declare ARGs after FROM so they're available in the build stage.
ARG AIRFLOW_VERSION
ARG PYTHON_VERSION

# Persist the constraints URL into the image. ENV survives into downstream
# builds (unlike ARG), so ONBUILD steps below can reference it when a
# customer's Dockerfile uses FROM this image.
ENV SKALEDATA_AIRFLOW_CONSTRAINTS_URL=https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt

# Airbyte provider is required for the bearer-auth shim. Pinned via the
# Airflow constraints file so the install never drifts the rest of the
# image's pinned dep tree.
RUN pip install --no-cache-dir \
       --constraint "${SKALEDATA_AIRFLOW_CONSTRAINTS_URL}" \
       "apache-airflow-providers-airbyte"

COPY --chown=airflow:0 package/ /tmp/skale-airflow-plugins/
RUN pip install --no-cache-dir /tmp/skale-airflow-plugins \
  && rm -rf /tmp/skale-airflow-plugins

# Default FAB auth-manager config. SkaleData proxies validate the sdk_*
# API key at the edge, so an inner login screen would just be noise.
# Customers who want a stricter internal model override this by COPYing
# their own webserver_config.py in their Dockerfile or by mounting one
# at /opt/airflow/webserver_config.py — both wins over this baked-in
# default.
COPY --chown=airflow:0 webserver_config.py /opt/airflow/webserver_config.py

# ----------------------------------------------------------------------------
# ONBUILD triggers — auto-pick-up of packages.txt + requirements.txt
# ----------------------------------------------------------------------------
# When a customer's Dockerfile does `FROM ghcr.io/skaledata/airflow:<tag>`,
# these triggers fire in order before the customer's own instructions:
#
#   1. If `packages.txt` exists alongside the customer's Dockerfile, every
#      line in it gets installed via `apt-get install`.
#   2. If `requirements.txt` exists alongside the customer's Dockerfile,
#      it gets installed via `pip install` under the upstream Airflow
#      constraints file (so customer deps can't break the base image's
#      carefully-pinned dependency tree).
#
# Both files are optional. The `*.tx[t]` glob trick makes the COPY a no-op
# when the file is absent (Docker accepts unmatched globs silently;
# unmatched literal filenames would error).
#
# Convention matches Astronomer's Astro Runtime: requirements.txt for pip,
# packages.txt for apt. Customers migrating from Astro need zero changes.

# packages.txt — apt install (runs as root)
#
# The grep filter strips `#` comments and blank lines so a scaffolded
# packages.txt with commented-out examples doesn't make apt try to install
# the comment text. `|| true` keeps the pipeline from failing under
# `pipefail` when grep produces zero matches.
ONBUILD USER root
ONBUILD COPY --chown=airflow:0 packages.tx[t] /tmp/skaledata-onbuild/
ONBUILD RUN PKGS=$(grep -v '^\s*#' /tmp/skaledata-onbuild/packages.txt 2>/dev/null | grep -v '^\s*$' || true); \
            if [ -n "$PKGS" ]; then \
              apt-get update && \
              echo "$PKGS" | xargs apt-get install -y --no-install-recommends && \
              apt-get clean && rm -rf /var/lib/apt/lists/*; \
            fi && rm -rf /tmp/skaledata-onbuild

# requirements.txt — pip install (runs as airflow)
#
# Same comment/blank filter as packages.txt above. Pip's `-r` already
# ignores `#` lines on its own, but we mirror the check here so we don't
# fork a pip process when the file is comments-only.
#
# We deliberately do NOT pass --constraint. Apache's Airflow constraints
# files pin specific provider versions; layering them on top of customer
# requirements.txt blocks legitimate version bumps (e.g. picking a
# newer provider release than the constraints file knows about) without
# adding much safety — the base image's own Airflow install is already
# pinned with constraints at build time, and customer-side breakage from
# their own pip pins is exactly what a customer would expect.
# Matches Astronomer's astro-runtime behaviour.
ONBUILD USER airflow
ONBUILD COPY --chown=airflow:0 requirements.tx[t] /tmp/skaledata-onbuild/
ONBUILD RUN REQS=$(grep -v '^\s*#' /tmp/skaledata-onbuild/requirements.txt 2>/dev/null | grep -v '^\s*$' || true); \
            if [ -n "$REQS" ]; then \
              pip install --no-cache-dir -r /tmp/skaledata-onbuild/requirements.txt; \
            fi && rm -rf /tmp/skaledata-onbuild

LABEL org.opencontainers.image.source="https://github.com/skaledata/airflow-base"
LABEL org.opencontainers.image.description="SkaleData-managed Airflow base image. Pre-installs skaledata-airflow-plugins (Airbyte bearer-auth shim) and auto-picks-up packages.txt + requirements.txt from the downstream build context (Astronomer-compatible convention)."
LABEL org.opencontainers.image.licenses="Apache-2.0"
