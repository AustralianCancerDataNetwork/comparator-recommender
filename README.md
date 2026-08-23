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

## Where future implementation belongs

The scaffold separates four small responsibilities:

- `config.py` declares operator-controlled settings and references to shared OA
  resources.
- `adapters.py` owns connections and database queries. This is the Python
  equivalent of the code that obtains and normalises data before an R analysis.
- `services.py` owns comparator lookup, ranking, and recommendation rules. It
  receives ordinary Python values from adapters and should not contain MCP code.
- `tools.py` exposes service operations to agents. Tools should be thin wrappers,
  not a second implementation of the analysis.

`plugin.py` is the composition root: Groundworkers calls it once during startup
to connect configuration to adapters and services, then asks it to register the
tools. Business logic should not be implemented inside `build()`.
