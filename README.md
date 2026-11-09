# Comparator Recommender

A [Groundworkers](https://github.com/AustralianCancerDataNetwork/groundworkers) plugin that suggests comparator cohorts for a study. Give it a target cohort and it returns the cohorts most similar to it, ranked by similarity and filtered by how many databases support each pairing.

The plugin does not compute cohort similarity itself. It serves a catalogue that you load from two CSV files: one listing cohorts, one listing pairwise similarity scores between them.

## Install

```console
uv add comparator-recommender
```

or `pip install comparator-recommender`. Groundworkers discovers the plugin automatically once it is installed in the same environment.

## Requirements

- Python 3.12 or later
- Groundworkers 0.7 or later
- PostgreSQL with the [pgvector](https://github.com/pgvector/pgvector) extension available. The plugin runs `CREATE EXTENSION IF NOT EXISTS vector`on first load, so the database user needs permission to do that, or an administrator must enable the extension beforehand.
- An embedding model, if you want to look up target cohorts by name. Either the model Groundworkers already uses or one you configure for this plugin.

## Configure

Run the Groundworkers setup console and open **Comparator Recommender**:

```console
groundworkers tui
```

It writes a section like this to your Groundworkers configuration file:

```toml
[databases.comparator_db]
kind = "generic"
connection = "cdm_main"        # any [connections.*] entry pointing at PostgreSQL
schema_name = "comparator"     # the schema must already exist

[tools.comparator_recommender]
comparator_db = "comparator_db"
# embedding_model_name = "embedding_model"   # optional; defaults to the Groundworkers model
# min_databases_default = 1                  # optional
```

| Setting | Default | Meaning |
|---|---|---|
| `comparator_db` | `comparator_db` | The `[databases.*]` entry that holds the catalogue. |
| `embedding_model_name` | unset | A `[models.*]` entry for target lookup. When unset, the Groundworkers embedding model is used. |
| `min_databases_default` | `1` | Ignore comparator pairs seen in fewer databases than this, unless a request overrides it. |

See the Groundworkers
[configuration guide](https://github.com/AustralianCancerDataNetwork/groundworkers/blob/main/docs/usage/configuration.md) for `[connections.*]`, `[databases.*]` and `[models.*]` entries.

## Load your data

The setup console has two steps under **Comparator Recommender**. Run them in order:

1. **Load comparator source.** Choose the cohort CSV and the similarity CSV. Each load replaces the whole catalogue.
2. **Create comparator embeddings.** Generates a vector for every cohort name so cohorts can be found by name. Re-run this after every load.

Then select **Verify**. It reports whether the database, tables, embeddings, vector index and model are ready.

### CSV format

Both files may be plain `.csv` or gzipped `.csv.gz`, with a header row.

**Cohort file**, one row per cohort:

| Column | Type | Meaning |
|---|---|---|
| `cohort_definition_id` | integer | Unique cohort ID. |
| `cohort_name` | text | Human-readable name. Required for every row: embedding fails if any name is empty. |
| `database_count` | integer | Number of databases the cohort was observed in. |

**Similarity file**, one row per cohort pair:

| Column | Type | Meaning |
|---|---|---|
| `cohort_definition_id_1` | integer | One cohort in the pair. |
| `cohort_definition_id_2` | integer | The other cohort. |
| `mean_cosine_similarity` | number | Similarity score; higher means more alike. |
| `database_count` | integer | Number of databases contributing to the score. |

Pairs are undirected: list each pair once, in either order. A pair is found whichever of its cohorts is the target, so listing it in both orders returns the comparator twice.

## Tools

Once loaded, Groundworkers exposes three tools to agents and MCP clients:

| Tool | Inputs | Returns |
|---|---|---|
| `comparator_recommender_find_target` | `name`, `top_n` (default 10) | Cohorts whose names are closest in meaning to `name`, with their IDs. |
| `comparator_recommender_recommend` | `target_id`, `top_n` (default 10), `min_databases` (optional) | The most similar comparator cohorts for that target, with similarity scores. |
| `comparator_recommender_status` | none | The same readiness report as **Verify**. |

A typical session: find the target cohort by name, then pass its ID to `comparator_recommender_recommend`.

## Troubleshooting

- **"Target lookup requires an embedding model"**: neither the plugin nor Groundworkers has an embedding model configured. Set `embedding_model_name`, or configure a Groundworkers embedding model.
- **"Every comparator cohort source row must have a cohort name"**: the cohort CSV has blank `cohort_name` values. Fix the file and load it again.
- **Name lookup returns nothing after a reload**: loading replaces the catalogue, including its embeddings. Run **Create comparator embeddings** again.
- **Results look wrong after changing models**: vectors made with one model can't be searched with another. Keep the same model for creating and looking up, or re-run **Create comparator embeddings** after switching.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
