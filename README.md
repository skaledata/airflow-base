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
