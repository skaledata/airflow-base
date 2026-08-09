"""In-image checks for the baked-in DataHub Airflow plugin.

Runs only inside the built base image (dockerfile-build matrix sets
IN_IMAGE_BUILD=1), where acryl-datahub-airflow-plugin is installed — it's
baked in via the Dockerfile, not a dependency of this package, so it's absent
on the host lint-and-test job. The gate is an env var, NOT importorskip: a
resolver backtrack to the ancient Airflow-2-only 0.14.x release can fail to
import under Airflow 3, and importorskip would swallow that ImportError and
silently skip — masking the exact failure these tests exist to catch.
"""

from __future__ import annotations

import os
from importlib.metadata import entry_points, version

import pytest

if not os.environ.get("IN_IMAGE_BUILD"):
    pytest.skip("runs only inside the built base image", allow_module_level=True)


def test_datahub_plugin_pinned_to_1_7_0() -> None:
    # A resolver backtrack (the failure the constraints tweak prevents) lands
    # an ancient 0.14.x with no Airflow 3 support — assert the exact pin.
    assert version("acryl-datahub-airflow-plugin") == "1.7.0"


def test_datahub_plugin_imports_under_airflow3() -> None:
    # The backtracked releases fail to import against Airflow 3; a clean import
    # proves the installed build is Airflow-3-compatible.
    import datahub_airflow_plugin  # noqa: F401


def test_datahub_plugin_registers_airflow_entrypoint() -> None:
    # A pip-installed Airflow plugin is only discovered via an entry point;
    # confirm the package contributes one pointing at its own module (scan all
    # groups so this doesn't hard-code plugin-vs-listener registration details).
    refs = [ep for ep in entry_points() if "datahub_airflow_plugin" in ep.value]
    assert refs, "acryl-datahub-airflow-plugin registered no Airflow entry point"
