# Comparator Recommender

This package is an installable Groundworkers plugin for finding target cohorts
and recommending pairwise comparators from a precomputed comparator catalogue.

It contributes two entry points:

- `omop.config` exposes `ComparatorRecommenderConfig` to oa-configurator.
- `groundworkers.plugins` exposes the plugin singleton to Groundworkers.

The configuration schema selects a generic comparator database, optionally selects an embedding model for target lookup, and sets the default minimum database support threshold. Groundworkers builds the setup-console workflow directly from this schema without plugin-specific TUI code.

The setup console also exposes the plugin's registered preparation steps:

- `Load comparator source` asks for the cohort and pairwise-similarity CSVs and loads them into the catalogue.
- `Create comparator embeddings` generates the stored vectors after the source is loaded.

The CSV paths are run arguments, not persistent plugin configuration. Both steps use Groundworkers' durable maintenance-run surface, so progress and logs appear with the core graph and embedding preparation runs.

Run the MWE against the sibling development branches:

```console
uv sync --group dev
uv run pytest
```

The acceptance test selects an existing CDM database, leaves the optional
embedding resources unconfigured, reviews the generated change, applies it, and
verifies the resulting `[tools.comparator_recommender]` section.

## Architecture

The package separates four responsibilities:

- `config.py` declares operator-controlled settings and references to shared OA
  resources.
- `adapters.py` owns the resolved database connection and backend.
- `models.py` reflects the two non-OMOP catalogue tables into SQLAlchemy mappings.
- `backends/postgresql.py` uses SQLAlchemy `select`, pgvector expressions,
  mapped row updates, and `Index` objects, with one isolated column migration
  for older catalogue tables. Its backend initialization follows the
  `omop-emb` lifecycle and ensures the pgvector extension before setup runs.
- `services.py` owns input policy and recommendation defaults. It receives
  ordinary Python values from adapters and contains no MCP code.
- `tools.py` exposes service operations to agents. Tools should be thin wrappers,
  not a second implementation of the analysis.

`plugin.py` is the composition root: Groundworkers calls it once during startup
to connect configuration to adapters and services, then asks it to register the
tools. Business logic should not be implemented inside `build()`.

The comparator catalogue is not an OMOP CDM table, so it should not be added to
`omop-alchemy`'s model registry. The local reflected mapping follows the same
SQLAlchemy model/query conventions while leaving the shared OMOP package focused
on CDM semantics.
