"""In-image checks for the baked-in DataHub Airflow plugin.

Skipped on the host lint-and-test job — acryl-datahub-airflow-plugin is only
installed in the built base image (via the Dockerfile), not a dependency of
this package. Runs inside the image in the dockerfile-build matrix, where it
guards the exact failure mode the setuptools-constraint tweak fixes: pip
silently backtracking the plugin to an ancient Airflow-2-only 0.14.x release.
"""

from __future__ import annotations

from importlib.metadata import entry_points, version

import pytest

pytest.importorskip("datahub_airflow_plugin")


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
    eps = entry_points()
    refs = [
        ep
        for grp in eps.groups
        for ep in eps.select(group=grp)
        if "datahub_airflow_plugin" in ep.value
    ]
    assert refs, "acryl-datahub-airflow-plugin registered no Airflow entry point"
