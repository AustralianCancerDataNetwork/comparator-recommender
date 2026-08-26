"""PostgreSQL/pgvector comparator catalogue backend.

Retrieval and row updates use reflected SQLAlchemy mappings. The database is
expected to have pgvector installed before comparator setup runs.
"""

from __future__ import annotations

import gzip
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
from groundworkers.base.errors import GroundworkersError
from groundworkers.plugins import (
    PluginReadinessField,
    PluginReadinessResult,
    PluginReadinessState,
)
from omop_emb.interface import EmbeddingReaderInterface, EmbeddingRole
from sqlalchemy import (
    DDL,
    Index,
    MetaData,
    Table,
    delete,
    func,
    inspect,
    literal,
    select,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from comparator_recommender.backends.base import ComparatorSelectorBackend
from comparator_recommender.models import ComparatorModels, has_column


class PostgresComparatorSelectorBackend(ComparatorSelectorBackend):
    """Read and maintain the ``cs_cohort``/``cs_similarity`` tables."""

    def pre_initialise_store(self) -> None:
        """Ensure pgvector is available before catalogue setup begins.

        This mirrors ``omop-emb``'s pgvector backend lifecycle. The dialect
        guard keeps lightweight SQLite fixtures usable even though this backend
        is intended for PostgreSQL deployments.
        """
        if self.engine.dialect.name != "postgresql":
            return
        with self.engine.begin() as connection:
            connection.execute(DDL("CREATE EXTENSION IF NOT EXISTS vector CASCADE"))

    def _models(self) -> ComparatorModels:
        return ComparatorModels.reflect(self.engine, self.schema)

    def _model(self):
        if self.model_backend_factory is None:
            raise GroundworkersError(
                "BACKEND_UNAVAIL",
                "Target lookup requires an embedding model. Configure one in Groundworkers or the plugin.",
            )
        return self.model_backend_factory()

    def find_target(self, name: str, top_n: int) -> list[tuple[int, str]]:
        embedding = EmbeddingReaderInterface.generate_embeddings(
            self._model(), name, role=EmbeddingRole.QUERY
        )
        if not has_column(self.engine, self.schema, "cs_cohort", "embedding_vector"):
            raise GroundworkersError(
                "BACKEND_UNAVAIL",
                f"{self.schema}.cs_cohort lacks embedding_vector; create comparator embeddings first.",
            )
        models = self._models()
        vector = models.cohort_table.c.embedding_vector
        statement = (
            select(
                models.cohort_table.c.cohort_definition_id,
                models.cohort_table.c.cohort_name,
            )
            .where(vector.is_not(None))
            .order_by(vector.cosine_distance(embedding[0].tolist()))
            .limit(top_n)
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).all()
        return [(int(cohort_id), str(cohort_name)) for cohort_id, cohort_name in rows]

    def recommend_comparators(
        self, target_id: int, top_n: int, min_databases: int
    ) -> list[tuple[float, str]]:
        from sqlalchemy import case, or_

        models = self._models()
        similarity = models.similarity_table
        cohort = models.cohort_table
        comparator_id = case(
            (
                similarity.c.cohort_definition_id_1 == target_id,
                similarity.c.cohort_definition_id_2,
            ),
            else_=similarity.c.cohort_definition_id_1,
        )
        statement = (
            select(similarity.c.mean_cosine_similarity, cohort.c.cohort_name)
            .select_from(
                similarity.join(cohort, cohort.c.cohort_definition_id == comparator_id)
            )
            .where(
                or_(
                    similarity.c.cohort_definition_id_1 == target_id,
                    similarity.c.cohort_definition_id_2 == target_id,
                )
            )
            .where(similarity.c.database_count >= min_databases)
            .order_by(
                similarity.c.mean_cosine_similarity.desc(), cohort.c.cohort_name.asc()
            )
            .limit(top_n)
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).all()
        return [(float(score), str(name)) for score, name in rows]

    def insert_data(self, cohort_table_path: str, similarity_table_path: str) -> None:
        self.pre_initialise_store()
        self.ensure_catalogue_schema()
        cohort_df = _read_csv(cohort_table_path)
        similarity_df = _read_csv(similarity_table_path)
        if not has_column(self.engine, self.schema, "cs_cohort", "embedding_vector"):
            raise RuntimeError(
                f"{self.schema}.cs_cohort lacks embedding_vector; run an explicit comparator schema migration first."
            )
        with self.engine.begin() as connection:
            models = self._models()
            connection.execute(delete(models.cohort_table))
            connection.execute(delete(models.similarity_table))
            cohort_df.to_sql(
                "cs_cohort",
                connection,
                schema=self.schema,
                if_exists="append",
                index=False,
            )
            similarity_df.to_sql(
                "cs_similarity",
                connection,
                schema=self.schema,
                if_exists="append",
                index=False,
            )
            _create_btree_index(
                connection,
                models.cohort_table,
                "cs_cohort_id_idx",
                "cohort_definition_id",
            )
            _create_btree_index(
                connection,
                models.similarity_table,
                "cs_similarity_target_idx",
                "cohort_definition_id_1",
            )
            _create_btree_index(
                connection,
                models.similarity_table,
                "cs_similarity_comparator_idx",
                "cohort_definition_id_2",
            )

    def create_embedding_vectors(self) -> None:
        if not has_column(self.engine, self.schema, "cs_cohort", "embedding_vector"):
            raise RuntimeError(
                f"{self.schema}.cs_cohort lacks embedding_vector; run an explicit comparator schema migration first."
            )
        models = self._models()
        with Session(self.engine) as session, session.begin():
            cohort_count = session.scalar(
                select(func.count()).select_from(models.cohort_table)
            )
            similarity_count = session.scalar(
                select(func.count()).select_from(models.similarity_table)
            )
            if not cohort_count or not similarity_count:
                raise RuntimeError(
                    "Load non-empty comparator cohort and similarity source data "
                    "before creating embeddings."
                )
            rows = (
                session.execute(
                    select(models.cohort)
                    .where(models.cohort.cohort_name.is_not(None))
                    .order_by(models.cohort.cohort_definition_id)
                )
                .scalars()
                .all()
            )
            if len(rows) != cohort_count:
                raise RuntimeError(
                    "Every comparator cohort source row must have a cohort name "
                    "before creating embeddings."
                )
            embeddings = EmbeddingReaderInterface.generate_embeddings(
                self._model(),
                [str(row.cohort_name) for row in rows],
                role=EmbeddingRole.DOCUMENT,
            )
            _ensure_vector_dimensions(
                session.connection(),
                models.cohort_table,
                embeddings.shape[1],
            )
            for row, embedding in zip(rows, embeddings, strict=True):
                row.embedding_vector = embedding.tolist()
            _create_vector_index(session, models.cohort_table)

    def verify_readiness(self) -> PluginReadinessResult:
        """Inspect catalogue, embeddings, index, and model without mutation."""

        fields: list[PluginReadinessField] = []
        try:
            with self.engine.connect() as connection:
                connection.execute(select(literal(1)))
                inspector = inspect(connection)
                fields.append(
                    _field(
                        "database_connection",
                        "Database connection",
                        "Connected",
                        PluginReadinessState.READY,
                        "The comparator database accepted a read-only query.",
                    )
                )
                cohort_exists = inspector.has_table("cs_cohort", schema=self.schema)
                similarity_exists = inspector.has_table(
                    "cs_similarity", schema=self.schema
                )
                fields.extend(
                    (
                        _presence_field("cohort_table", "Cohort table", cohort_exists),
                        _presence_field(
                            "similarity_table",
                            "Similarity table",
                            similarity_exists,
                        ),
                    )
                )
                cohort_table = (
                    Table(
                        "cs_cohort",
                        MetaData(),
                        schema=self.schema,
                        autoload_with=connection,
                    )
                    if cohort_exists
                    else None
                )
                similarity_table = (
                    Table(
                        "cs_similarity",
                        MetaData(),
                        schema=self.schema,
                        autoload_with=connection,
                    )
                    if similarity_exists
                    else None
                )
                cohort_count = _count_rows(connection, cohort_table)
                similarity_count = _count_rows(connection, similarity_table)
                fields.extend(
                    (
                        _count_field("cohort_rows", "Cohort rows", cohort_count),
                        _count_field(
                            "similarity_rows",
                            "Similarity rows",
                            similarity_count,
                        ),
                    )
                )
                embedding_column = bool(
                    cohort_exists
                    and any(
                        column["name"] == "embedding_vector"
                        for column in inspector.get_columns(
                            "cs_cohort", schema=self.schema
                        )
                    )
                )
                fields.append(
                    _presence_field(
                        "embedding_column",
                        "Embedding column",
                        embedding_column,
                    )
                )
                populated = (
                    connection.scalar(
                        select(func.count())
                        .select_from(cohort_table)
                        .where(cohort_table.c.embedding_vector.is_not(None))
                    )
                    if cohort_table is not None and embedding_column
                    else None
                )
                fields.append(_embedding_count_field(populated, cohort_count))
                vector_index = bool(
                    cohort_exists
                    and embedding_column
                    and _has_hnsw_vector_index(
                        inspector.get_indexes("cs_cohort", schema=self.schema),
                        postgresql=self.engine.dialect.name == "postgresql",
                    )
                )
                fields.append(
                    _presence_field(
                        "vector_index",
                        "HNSW vector index",
                        vector_index,
                    )
                )
        except SQLAlchemyError:
            fields = [
                _field(
                    "database_connection",
                    "Database connection",
                    "Unavailable",
                    PluginReadinessState.ERROR,
                    "The comparator database could not be queried; review host logs.",
                ),
                *_unchecked_catalogue_fields(),
            ]

        fields.append(self._model_readiness())
        state = _overall_state(fields)
        if state is PluginReadinessState.READY:
            summary = "Comparator catalogue, embeddings, index, and model are ready."
        elif state is PluginReadinessState.ERROR:
            summary = "Comparator verification found an operational error."
        else:
            summary = (
                "Comparator is configured but setup is incomplete. Load source data "
                "before creating embeddings."
            )
        return PluginReadinessResult(
            state=state,
            summary=summary,
            fields=tuple(fields),
        )

    def _model_readiness(self) -> PluginReadinessField:
        if self.model_backend_factory is None:
            return _field(
                "embedding_model",
                "Embedding model",
                "Not configured",
                PluginReadinessState.WARNING,
                "Configure a plugin-specific or shared Groundworkers embedding model.",
            )
        try:
            model = self.model_backend_factory()
            # Groundworkers' TUI runs inside Textual's event loop. any-llm's
            # synchronous list_models API otherwise rejects that context and
            # ModelBackend.is_available() turns the rejection into False.
            # Allow any-llm to bridge the probe through its worker thread.
            availability_kwargs: dict[str, object] = {"allow_running_loop": True}
            if getattr(model, "provider", None) != "ollama":
                availability_kwargs["timeout"] = 5.0
            available = model.capabilities.embeddings and model.is_available(
                **availability_kwargs
            )
        except Exception:
            available = False
        if not available:
            return _field(
                "embedding_model",
                "Embedding model",
                "Unavailable",
                PluginReadinessState.ERROR,
                "The configured embedding model/provider could not be reached or does not support embeddings.",
            )
        return _field(
            "embedding_model",
            "Embedding model",
            self.model_source or "Available",
            PluginReadinessState.READY,
            "A configured or shared embedding model backend is available.",
        )

    def ensure_catalogue_schema(self) -> None:
        """Create catalogue tables and apply the legacy vector-column migration.

        The pgvector prerequisite is handled by ``pre_initialise_store``;
        this method only repairs an older catalogue table that predates its
        vector column.
        """
        with self.engine.begin() as connection:
            if inspect(connection).has_table(
                "cs_cohort", schema=self.schema
            ) and not has_column(
                self.engine, self.schema, "cs_cohort", "embedding_vector"
            ):
                connection.execute(
                    DDL(
                        f"ALTER TABLE {_qualified(self.schema, 'cs_cohort')} "
                        'ADD COLUMN "embedding_vector" HALFVEC'
                    )
                )
        ComparatorModels.create_catalogue_tables(self.engine, self.schema)
        self._upgrade_identifier_columns()

    def _upgrade_identifier_columns(self) -> None:
        """Widen catalogue identifiers for OMOP-sized cohort IDs.

        Early versions created these columns as PostgreSQL ``INTEGER``. The
        source catalogue contains IDs larger than 2^31, so keep existing
        installations compatible with the current ``BIGINT`` model before
        loading source rows. The alteration is PostgreSQL-specific; SQLite
        fixtures already receive the correct type from ``create_all``.
        """
        if self.engine.dialect.name != "postgresql":
            return
        with self.engine.begin() as connection:
            for table, columns in (
                (
                    "cs_cohort",
                    ("cohort_definition_id",),
                ),
                (
                    "cs_similarity",
                    ("cohort_definition_id_1", "cohort_definition_id_2"),
                ),
            ):
                for column in columns:
                    connection.execute(
                        DDL(
                            f"ALTER TABLE {_qualified(self.schema, table)} "
                            f'ALTER COLUMN "{column}" TYPE BIGINT'
                        )
                    )


def _read_csv(path: str) -> pd.DataFrame:
    source = Path(path)
    if source.suffix == ".gz":
        with gzip.open(source, "rt") as stream:
            return pd.read_csv(stream)
    return pd.read_csv(source)


def _create_btree_index(connection: Any, table: Any, name: str, column: str) -> None:
    Index(name, table.c[column]).create(connection, checkfirst=True)


def _create_vector_index(session: Session, table: Any) -> None:
    Index(
        "cs_cohort_embedding_idx",
        table.c.embedding_vector,
        postgresql_using="hnsw",
        postgresql_ops={"embedding_vector": "halfvec_cosine_ops"},
        postgresql_with={"m": 16, "ef_construction": 64},
    ).create(session.connection(), checkfirst=True)


def _ensure_vector_dimensions(connection: Any, table: Table, dimensions: int) -> None:
    """Set the pgvector halfvec dimension required by an HNSW index.

    The catalogue table is created before the configured embedding model is
    called, so its initial ``halfvec`` column is intentionally unbounded. Once
    embeddings are available, PostgreSQL requires a declared dimension for an
    HNSW operator class. The operation is PostgreSQL-specific; SQLite test
    fixtures use a regular integer placeholder for the embedding column.
    """
    if connection.dialect.name != "postgresql":
        return
    if dimensions <= 0:
        raise RuntimeError("The embedding model returned vectors with no dimensions.")
    qualified_table = _qualified(table.schema or "public", table.name)
    connection.execute(
        DDL(
            f"ALTER TABLE {qualified_table} "
            'ALTER COLUMN "embedding_vector" '
            f"TYPE halfvec({dimensions}) "
            'USING "embedding_vector"::halfvec('
            f"{dimensions})"
        )
    )


def _qualified(schema: str, table: str) -> str:
    return f'"{schema.replace(chr(34), chr(34) * 2)}"."{table}"'


def _field(
    key: str,
    label: str,
    value: str,
    state: PluginReadinessState,
    detail: str,
) -> PluginReadinessField:
    return PluginReadinessField(key, label, value, state, detail)


def _presence_field(key: str, label: str, present: bool) -> PluginReadinessField:
    return _field(
        key,
        label,
        "Present" if present else "Missing",
        PluginReadinessState.READY if present else PluginReadinessState.WARNING,
        (
            f"{label} is present."
            if present
            else f"{label} is missing; run Load comparator source."
        ),
    )


def _count_rows(connection: Any, table: Table | None) -> int | None:
    if table is None:
        return None
    return int(connection.scalar(select(func.count()).select_from(table)) or 0)


def _count_field(key: str, label: str, count: int | None) -> PluginReadinessField:
    if count is None:
        return _field(
            key,
            label,
            "Not checked",
            PluginReadinessState.WARNING,
            f"{label} cannot be counted until its table exists.",
        )
    return _field(
        key,
        label,
        str(count),
        PluginReadinessState.READY if count > 0 else PluginReadinessState.WARNING,
        f"{count} row(s) are loaded."
        if count > 0
        else "No source rows are loaded; run Load comparator source.",
    )


def _embedding_count_field(
    populated: int | None,
    cohort_count: int | None,
) -> PluginReadinessField:
    if populated is None or cohort_count is None:
        return _field(
            "populated_embeddings",
            "Populated embeddings",
            "Not checked",
            PluginReadinessState.WARNING,
            "Embedding population requires the cohort table and embedding column.",
        )
    complete = cohort_count > 0 and populated == cohort_count
    return _field(
        "populated_embeddings",
        "Populated embeddings",
        f"{populated} / {cohort_count}",
        PluginReadinessState.READY if complete else PluginReadinessState.WARNING,
        (
            "Every cohort row has an embedding."
            if complete
            else "Create embeddings after non-empty source data has been loaded."
        ),
    )


def _has_hnsw_vector_index(
    indexes: Sequence[Mapping[str, Any]],
    *,
    postgresql: bool,
) -> bool:
    """Recognize the SQLAlchemy-inspected pgvector HNSW index.

    PostgreSQL exposes its access method through ``dialect_options``. Other
    dialects are accepted by stable name/column for lightweight test fixtures.
    No PostgreSQL catalogue SQL is required.
    """

    for index in indexes:
        if index.get("name") != "cs_cohort_embedding_idx":
            continue
        if "embedding_vector" not in (index.get("column_names") or ()):
            continue
        if not postgresql:
            return True
        options = index.get("dialect_options") or {}
        return options.get("postgresql_using") == "hnsw"
    return False


def _unchecked_catalogue_fields() -> list[PluginReadinessField]:
    return [
        _field(
            key,
            label,
            "Not checked",
            PluginReadinessState.WARNING,
            "Restore database connectivity, then verify again.",
        )
        for key, label in (
            ("cohort_table", "Cohort table"),
            ("similarity_table", "Similarity table"),
            ("cohort_rows", "Cohort rows"),
            ("similarity_rows", "Similarity rows"),
            ("embedding_column", "Embedding column"),
            ("populated_embeddings", "Populated embeddings"),
            ("vector_index", "HNSW vector index"),
        )
    ]


def _overall_state(fields: list[PluginReadinessField]) -> PluginReadinessState:
    if any(field.state is PluginReadinessState.ERROR for field in fields):
        return PluginReadinessState.ERROR
    if any(field.state is not PluginReadinessState.READY for field in fields):
        return PluginReadinessState.WARNING
    return PluginReadinessState.READY
