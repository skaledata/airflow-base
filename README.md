# SkaleData Airflow base image

Maintained, drop-in replacement for `apache/airflow` that bakes in the
[`airflow-provider-skaledata`](./package) package. Used by every SkaleData-managed
Airflow deployment by default.

```
ghcr.io/skaledata/airflow:<airflow-version>
```

The Python version is pinned internally (currently 3.12) and not part of the
customer-facing tag — we don't offer Python as a user choice.

## What's pre-installed

- `apache-airflow` (from `apache/airflow:<version>-python<version>`)
- `apache-airflow-providers-airbyte`
- `airflow-provider-skaledata` — see [package/README.md](./package/README.md)
- A default `webserver_config.py` at `/opt/airflow/webserver_config.py`
  (`AUTH_ROLE_PUBLIC = "Admin"`) — SkaleData proxies validate the
  `sdk_*` API key at the edge, so an internal login screen would just
  be noise. Override by COPYing your own `webserver_config.py` in your
  Dockerfile or by mounting one at `/opt/airflow/webserver_config.py` —
  both wins over the baked-in default.

## Auto-pick-up of `packages.txt` and `requirements.txt`

The image's [Dockerfile](./Dockerfile) declares `ONBUILD` triggers that fire when
a customer's downstream Dockerfile uses `FROM ghcr.io/skaledata/airflow:<tag>`.
Before any of the customer's own instructions run, the triggers:

1. Look for **`packages.txt`** alongside the customer's Dockerfile. If present,
   every line is installed via `apt-get install --no-install-recommends`.
2. Look for **`requirements.txt`** alongside the customer's Dockerfile. If
   present, it's installed via `pip install -r requirements.txt`. We do **not**
   pass `--constraint` here — Apache's constraints files pin specific provider
   versions and block legitimate customer bumps (e.g. picking a newer Airbyte
   provider release than the constraints know about). Matches Astronomer's
   astro-runtime behaviour. The base image's own Airflow install is still
   pinned with constraints at build time, so the platform layer stays stable.

Both files are optional. The simplest customer Dockerfile is one line:

```Dockerfile
FROM ghcr.io/skaledata/airflow:3.3.0
```

Convention matches [Astronomer's Astro Runtime](https://www.astronomer.io/docs/astro/cli/develop-project/#add-python-and-os-level-packages),
so customers migrating from Astro need zero config changes.

## Versioning

Image tags are pinned to upstream Airflow versions one-to-one:

| Tag              | Airflow | Notes                                                    |
| ---------------- | ------- | -------------------------------------------------------- |
| `3.3.0`          | 3.3.0   | Mutable — always the latest plugin for 3.3.0             |
| `3.3.0-<sha7>`   | 3.3.0   | Immutable — pin against this for prod                    |
| `3.2.2`          | 3.2.2   | Mutable — always the latest plugin for 3.2.2             |
| `3.2.2-<sha7>`   | 3.2.2   | Immutable — pin against this for prod                    |
| `latest`         | 3.3.0   | Floating — points at the entry flagged `latest` in [`versions.json`](./versions.json) |

Supported Airflow versions live in [`versions.json`](./versions.json) — that
file is the single source of truth for the CI matrix and the release
matrix. Adding a new Airflow version is one line there.

A plugin-only fix (no Airflow bump) re-publishes the mutable per-version tag
and a fresh immutable `-<sha7>` for every entry in `versions.json`. The
Airflow version doesn't move.

## Using a custom image as a SkaleData customer

If you maintain your own image (e.g. to install custom providers or DAG deps),
swap the base:

```Dockerfile
- FROM apache/airflow:3.3.0-python3.12
+ FROM ghcr.io/skaledata/airflow:3.3.0
```

The plugins are pre-installed and registered via Airflow entry points; no other
changes needed.

## Local development

Building the image locally requires both build args — there are no defaults
in the `Dockerfile` on purpose (so a naked `docker build` fails loudly
instead of silently building whatever the last hardcoded default was):

```bash
docker build \
  --build-arg AIRFLOW_VERSION=3.3.0 \
  --build-arg PYTHON_VERSION=3.12 \
  -t skaledata-airflow:local .
```

Pick the pair from [`versions.json`](./versions.json). The plugin's host-side
tests (fast) run from the `package/` dir:

```bash
cd package && pip install -e ".[dev]" && pytest
```

The full "does it build + do the ONBUILD triggers fire + does the plugin
import against this Airflow" check is what CI's `dockerfile-build` job does
end-to-end. To reproduce locally, walk through the steps in
[`.github/workflows/ci.yml`](./.github/workflows/ci.yml).

## Releasing

There are two independent release channels, distinguished by tag prefix:

| Tag prefix    | What it does                                            | Rebuilds images? | Publishes to PyPI? |
| ------------- | ------------------------------------------------------- | ---------------- | ------------------ |
| `image-v*`    | Rebuild every entry in `versions.json`, push to GHCR    | Yes              | No                 |
| `plugin-v*`   | Publish `airflow-provider-skaledata` from `package/`    | No               | Yes                |

### Adding a new Airflow version

1. Open a PR that adds one entry to [`versions.json`](./versions.json).
   Flip `latest: true` from the previous entry to the new one if this is
   the version that should back the floating `:latest` GHCR tag.
   ```json
   { "airflow": "3.3.1", "python": "3.12", "latest": true }
   ```
2. Wait for CI to go green — the new entry gets its own `dockerfile-build`
   matrix row that runs the plugin's `pytest` suite inside the built image,
   so version-drift breakage (e.g. an Airflow bump renaming a class the
   plugin subclasses) is caught here, not on the release tag.
3. Merge to `main`.
4. Cut an image release from `main`:
   ```bash
   git checkout main && git pull
   git tag image-v2026-07-06
   git push origin image-v2026-07-06
   ```
5. The [Release workflow](./.github/workflows/release.yml) builds every
   entry in `versions.json` and pushes `<airflow-version>`,
   `<airflow-version>-<sha7>`, and (for the `latest`-flagged entry)
   `:latest` to GHCR.

The tag body is a free-form marker (a date works well) — it doesn't affect
the GHCR image tags, which come from `versions.json`.

### Plugin-only release (`airflow-provider-skaledata` on PyPI)

1. Bump `version` in [`package/pyproject.toml`](./package/pyproject.toml),
   PR, merge.
2. Cut a tag that matches the new version exactly:
   ```bash
   git checkout main && git pull
   git tag plugin-v0.4.0
   git push origin plugin-v0.4.0
   ```
3. The workflow verifies the tag matches `pyproject.toml`'s `version`
   before publishing — mismatched tags fail the release loudly. This
   channel does **not** rebuild images.

### Plugin-only refresh of images (no new PyPI release, no Airflow bump)

Just cut an `image-v*` tag — every entry in `versions.json` gets rebuilt
against the current `main`, which bakes in whatever's at `package/` right
now.

### Coordinated release (new plugin + refreshed images)

Two tags, in order: `plugin-v0.4.0` first (so PyPI has the new version),
then `image-v...` (so the images bake it in from `main`).
