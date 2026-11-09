# Contributing

## Development setup

```console
uv sync --group dev
uv run pytest
uv run ruff check .
uv run ty check src/
```

The tests run against SQLite fixtures, so no PostgreSQL server is needed. The configuration test selects a database, leaves the embedding model unset,
applies the generated change and checks the resulting `[tools.comparator_recommender]` section.

Pull requests need exactly one of the labels `breaking`, `feature`, `fix` or `dependencies` (or `chore` to skip the check). The label decides the next version number in the draft release.

## Entry points

- `omop.config` exposes `ComparatorRecommenderConfig` to oa-configurator. Groundworkers builds the setup-console form directly from this schema; there is no plugin-specific TUI code.
- `groundworkers.plugins` exposes the `plugin` singleton to Groundworkers.

## Code layout

| Module | Responsibility |
|---|---|
| `config.py` | Operator settings and references to shared resources. |
| `adapters.py` | The resolved database connection and backend. |
| `models.py` | SQLAlchemy mappings reflected from the two catalogue tables. |
| `backends/postgresql.py` | Queries, pgvector expressions, indexes and the one column migration for older catalogue tables. Ensures the pgvector extension before setup, following the omop-emb lifecycle. |
| `services.py` | Input validation and recommendation defaults. No MCP code. |
| `tools.py` | MCP tool registration. |
| `plugin.py` | Composition root: wires config to adapters and services at startup, registers tools and declares the setup steps. |
| `setup_cli.py` | The out-of-process commands the setup steps run. |

## Conventions

- Tools stay thin wrappers over `services.py`. Don't put analysis logic in `tools.py`.
- Keep business logic out of `plugin.build()`; it only wires objects together.
- The comparator catalogue (`cs_cohort`, `cs_similarity`) is not an OMOP CDM table. Keep its mappings here, not in omop-alchemy's model registry.
- Comparator vectors live in `cs_cohort.embedding_vector`. They are generated directly from the configured model and do not use the shared omop-emb embedding-store registry.
- CSV paths are run arguments to the setup steps, not saved configuration.

## Releasing

1. Bump `version` in `pyproject.toml`.
2. Merge to `main`.
3. Push a matching tag, e.g. `v0.2.1`. The publish workflow uploads the package to PyPI.
