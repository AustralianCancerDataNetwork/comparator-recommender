# Comparator Recommender configuration MWE

This package is the smallest installed plugin that exercises Groundworkers'
generic plugin-configuration workflow. It deliberately contains no comparator
selection or recommendation implementation.

It contributes two entry points:

- `omop.config` exposes `ComparatorRecommenderConfig` to oa-configurator.
- `groundworkers.plugins` exposes the plugin singleton to Groundworkers.

The configuration schema has one required CDM database reference, two optional
embedding references, and one constrained scalar. Groundworkers therefore builds
the setup-console workflow directly from the schema without plugin-specific TUI
code.

Run the MWE against the sibling development branches:

```console
uv sync --group dev
uv run pytest
```

The acceptance test selects an existing CDM database, leaves the optional
embedding resources unconfigured, reviews the generated change, applies it, and
verifies the resulting `[tools.comparator_recommender]` section.
