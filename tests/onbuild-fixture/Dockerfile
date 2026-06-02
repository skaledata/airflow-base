# Test fixture used by CI to verify that the airflow-base ONBUILD triggers
# pick up packages.txt + requirements.txt from the customer's build context.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# That's it. The ONBUILD triggers in the base image install packages.txt
# (apt) and requirements.txt (pip) automatically — see this directory's
# packages.txt + requirements.txt for the test inputs.
