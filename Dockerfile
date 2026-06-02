ARG AIRFLOW_VERSION=3.2.1
ARG PYTHON_VERSION=3.12

FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}

# Re-declare ARGs after FROM so they're available in the build stage.
ARG AIRFLOW_VERSION
ARG PYTHON_VERSION

# Airbyte provider is required for the bearer-auth shim. Pinned via the
# Airflow constraints file so the install never drifts the rest of the
# image's pinned dep tree.
RUN AIRFLOW_CONSTRAINTS="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt" \
  && pip install --no-cache-dir \
       --constraint "${AIRFLOW_CONSTRAINTS}" \
       "apache-airflow-providers-airbyte"

COPY package/ /tmp/skaledata-airflow-plugins/
RUN pip install --no-cache-dir /tmp/skaledata-airflow-plugins \
  && rm -rf /tmp/skaledata-airflow-plugins

LABEL org.opencontainers.image.source="https://github.com/skaledata/airflow-base"
LABEL org.opencontainers.image.description="SkaleData-managed Airflow base image with the skaledata-airflow-plugins package (Airbyte bearer-auth shim) pre-installed."
LABEL org.opencontainers.image.licenses="Apache-2.0"
