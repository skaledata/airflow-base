# CLAUDE.md — airflow-base

Orientation for Claude Code sessions in this repo. Human-facing docs live in
[README.md](./README.md); code-review dimensions live in [.datadillo.md](./.datadillo.md).

## What this repo is

A custom Airflow base Docker image (`ghcr.io/skaledata/airflow`) that layers
on top of upstream `apache/airflow`, bakes in the `airflow-provider-skaledata`
plugin from `package/`, adds a default `webserver_config.py`, and declares
`ONBUILD` triggers that auto-install customer `packages.txt` + `requirements.txt`
(Astronomer-compatible convention).

Ships to customer clusters via the SkaleData Helm chart. The plugin also
publishes to PyPI as `airflow-provider-skaledata` for standalone use.

## Layout

```
versions.json               ← single source of truth for supported (airflow, python) pairs
Dockerfile                  ← builds ghcr.io/skaledata/airflow (no default ARGs — always pass build-args)
webserver_config.py         ← default FAB config baked into the image
package/                    ← the airflow-provider-skaledata plugin (published to PyPI)
  pyproject.toml            ← version lives here; plugin-v<X.Y.Z> tags must match this exactly
  skale/providers/airbyte/  ← Airbyte hook/operator/trigger drop-ins (bearer-auth shim)
  tests/                    ← host-side pytest suite (also re-run inside each image in CI)
tests/onbuild-fixture/      ← downstream Dockerfile that exercises ONBUILD triggers in CI
.github/workflows/
  ci.yml                    ← lint + pytest + per-version dockerfile-build matrix
  release.yml               ← two channels: image-v* and plugin-v*
```

## Non-obvious contracts

- **`versions.json` is the matrix source of truth.** Both `ci.yml` and
  `release.yml` derive their build matrices from it via a `setup-matrix` job
  that runs `jq -c '{include: .versions}'`. Adding an Airflow version = one
  line in `versions.json`. Do **not** duplicate the matrix in either workflow.
- **At most one entry may have `latest: true`.** Enforced in the `setup-matrix`
  step. That entry drives the floating `ghcr.io/skaledata/airflow:latest` GHCR tag.
- **`Dockerfile` has no default `ARG AIRFLOW_VERSION` / `PYTHON_VERSION`.**
  On purpose — a naked `docker build .` fails loudly instead of building whatever
  the last hardcoded default was. CI + release always pass them explicitly.
- **Two release tag prefixes, never `v*`.**
  - `image-v*` → rebuild every entry in `versions.json` to GHCR (mutable, immutable, `:latest`).
  - `plugin-v*` → publish `airflow-provider-skaledata` to PyPI via Trusted Publishing.
  - The plugin tag must exactly match `package/pyproject.toml`'s `version` — the workflow
    checks this and fails the publish otherwise.
- **CI runs the plugin's `pytest` suite inside each built image**, not just
  against the host Python. This is the pre-release signal for Airflow-version
  drift breaking the plugin (e.g. a bump renaming a class the plugin subclasses).

## Common tasks

**Add a new Airflow version.** Add an entry to `versions.json`, flipping
`latest: true` from the previous entry if appropriate. Open a PR — CI matrix
picks it up automatically. See README's "Adding a new Airflow version" for
the tag step.

**Cut a plugin patch.** Bump `package/pyproject.toml` `version`, PR, merge,
then push a `plugin-v<X.Y.Z>` tag from `main`. Does not rebuild images.

**Refresh images without a plugin release.** Just push an `image-v*` tag —
rebuilds every entry in `versions.json` from current `main`.

**Build the image locally.** `docker build --build-arg AIRFLOW_VERSION=<X> --build-arg PYTHON_VERSION=<Y> .`
Pick the pair from `versions.json`.

**Run the plugin tests locally.** `cd package && pip install -e ".[dev]" && pytest`.

## Review dimensions

See [.datadillo.md](./.datadillo.md) — highest-signal review dimensions
(Airflow compat, Dockerfile reproducibility, provider version compat,
webserver_config auth, DAG parsing cost) and repo-specific gotchas
(no tenant-specific config, no hardcoded `AIRFLOW__CORE__EXECUTOR`, no
`airflow db migrate` at build time).
