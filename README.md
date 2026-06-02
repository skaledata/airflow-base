# SkaleData Airflow base image

Maintained, drop-in replacement for `apache/airflow` that bakes in the
[`skaledata-airflow-plugins`](./package) package. Used by every SkaleData-managed
Airflow deployment by default.

```
ghcr.io/skaledata/airflow:<airflow-version>
```

The Python version is pinned internally (currently 3.12) and not part of the
customer-facing tag — we don't offer Python as a user choice.

## What's pre-installed

- `apache-airflow` (from `apache/airflow:<version>-python<version>`)
- `apache-airflow-providers-airbyte`
- `skaledata-airflow-plugins` — see [package/README.md](./package/README.md)

## Auto-pick-up of `packages.txt` and `requirements.txt`

The image's [Dockerfile](./Dockerfile) declares `ONBUILD` triggers that fire when
a customer's downstream Dockerfile uses `FROM ghcr.io/skaledata/airflow:<tag>`.
Before any of the customer's own instructions run, the triggers:

1. Look for **`packages.txt`** alongside the customer's Dockerfile. If present,
   every line is installed via `apt-get install --no-install-recommends`.
2. Look for **`requirements.txt`** alongside the customer's Dockerfile. If
   present, it's installed via `pip install --constraint <airflow-constraints>`
   so customer deps can't break the base image's carefully-pinned dep tree.

Both files are optional. The simplest customer Dockerfile is one line:

```Dockerfile
FROM ghcr.io/skaledata/airflow:3.2.2
```

Convention matches [Astronomer's Astro Runtime](https://www.astronomer.io/docs/astro/cli/develop-project/#add-python-and-os-level-packages),
so customers migrating from Astro need zero config changes.

## Versioning

Image tags are pinned to upstream Airflow versions one-to-one:

| Tag              | Airflow | Notes                                          |
| ---------------- | ------- | ---------------------------------------------- |
| `3.2.2`          | 3.2.2   | Mutable — always the latest plugin for 3.2.2   |
| `3.2.2-<sha7>`   | 3.2.2   | Immutable — pin against this for prod          |

A plugin-only fix (no Airflow bump) re-publishes the mutable `3.2.2` tag and a
fresh immutable `-<sha7>`. The Airflow version doesn't move.

## Using a custom image as a SkaleData customer

If you maintain your own image (e.g. to install custom providers or DAG deps),
swap the base:

```Dockerfile
- FROM apache/airflow:3.2.2-python3.12
+ FROM ghcr.io/skaledata/airflow:3.2.2
```

The plugins are pre-installed and registered via Airflow entry points; no other
changes needed.

## Releasing

1. Bump `package/pyproject.toml` `version` if the plugin changed.
2. Update the matrix in `.github/workflows/release.yml` if adding a new Airflow target.
3. Tag a release: `git tag v0.1.0 && git push origin v0.1.0`.
4. The release workflow builds + pushes every matrix entry to GHCR.
