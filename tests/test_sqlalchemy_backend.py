from unittest.mock import Mock

import pytest
from omop_llm import EmbeddingRole
from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import (
    BigInteger,
    Column,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    create_mock_engine,
    inspect,
    select,
)
from sqlalchemy.dialects import postgresql

from comparator_recommender.backends.postgresql import (
    PostgresComparatorSelectorBackend,
    _ensure_vector_dimensions,
)
from comparator_recommender.models import ComparatorModels


def test_catalogue_identifier_columns_are_bigint() -> None:
    engine = create_engine("sqlite://")

    ComparatorModels.create_catalogue_tables(engine, "main")

    columns = {
        table: {
            column["name"]: column["type"]
            for column in inspect(engine).get_columns(table, schema="main")
        }
        for table in ("cs_cohort", "cs_similarity")
    }
    assert isinstance(columns["cs_cohort"]["cohort_definition_id"], BigInteger)
    assert isinstance(
        columns["cs_similarity"]["cohort_definition_id_1"], BigInteger
    )
    assert isinstance(
        columns["cs_similarity"]["cohort_definition_id_2"], BigInteger
    )


def test_embedding_dimensions_are_declared_before_index_creation() -> None:
    statements: list[str] = []
    engine = create_mock_engine(
        "postgresql+psycopg://",
        lambda statement, *_args, **_kwargs: statements.append(
            str(statement.compile(dialect=engine.dialect))
        ),
    )
    table = Table(
        "cs_cohort",
        MetaData(),
        Column("embedding_vector", Integer),
        schema="public",
    )

    _ensure_vector_dimensions(engine, table, 1024)

    assert statements == [
        'ALTER TABLE "public"."cs_cohort" '
        'ALTER COLUMN "embedding_vector" TYPE halfvec(1024) '
        'USING "embedding_vector"::halfvec(1024)'
    ]


def test_target_distance_is_a_sqlalchemy_pgvector_expression() -> None:
    table = Table(
        "cs_cohort",
        MetaData(),
        Column("cohort_definition_id", Integer),
        Column("embedding_vector", HALFVEC(3)),
    )
    statement = select(table.c.cohort_definition_id).order_by(
        table.c.embedding_vector.cosine_distance([0.1, 0.2, 0.3])
    )

    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "<=>" in compiled
    assert "text(" not in compiled


def _catalogue(engine, *, rows: bool, embeddings: bool, vector_index: bool) -> None:
    metadata = MetaData()
    cohort = Table(
        "cs_cohort",
        metadata,
        Column("cohort_definition_id", Integer, primary_key=True),
        Column("cohort_name", String),
        Column("database_count", Integer),
        Column("embedding_vector", Integer),
    )
    similarity = Table(
        "cs_similarity",
        metadata,
        Column("cohort_definition_id_1", Integer, primary_key=True),
        Column("cohort_definition_id_2", Integer, primary_key=True),
        Column("mean_cosine_similarity", Integer),
        Column("database_count", Integer),
    )
    if vector_index:
        Index("cs_cohort_embedding_idx", cohort.c.embedding_vector)
    metadata.create_all(engine)
    if rows:
        with engine.begin() as connection:
            connection.execute(
                cohort.insert(),
                {
                    "cohort_definition_id": 1,
                    "cohort_name": "Example cohort",
                    "database_count": 2,
                    "embedding_vector": 1 if embeddings else None,
                },
            )
            connection.execute(
                similarity.insert(),
                {
                    "cohort_definition_id_1": 1,
                    "cohort_definition_id_2": 2,
                    "mean_cosine_similarity": 1,
                    "database_count": 2,
                },
            )


def _backend(engine, *, model: bool = True) -> PostgresComparatorSelectorBackend:
    class AvailableModel:
        class Capabilities:
            embeddings = True

        capabilities = Capabilities()

        def is_available(self, **_kwargs) -> bool:
            return True

    return PostgresComparatorSelectorBackend(
        engine,
        "main",
        model_backend_factory=(lambda: AvailableModel()) if model else None,
        model_source="Configured model: comparator_embeddings" if model else None,
    )


def _fields(report) -> dict[str, object]:
    return {field.key: field for field in report.fields}


def test_readiness_reports_missing_catalogue_without_mutating_database() -> None:
    engine = create_engine("sqlite://")

    report = _backend(engine).verify_readiness()

    assert report.state.value == "warning"
    assert _fields(report)["database_connection"].value == "Connected"
    assert _fields(report)["cohort_table"].value == "Missing"
    assert _fields(report)["similarity_table"].value == "Missing"
    assert inspect(engine).get_table_names() == []


def test_readiness_reports_loaded_source_before_embeddings() -> None:
    engine = create_engine("sqlite://")
    _catalogue(engine, rows=True, embeddings=False, vector_index=False)

    report = _backend(engine).verify_readiness()
    fields = _fields(report)

    assert report.state.value == "warning"
    assert fields["cohort_rows"].value == "1"
    assert fields["similarity_rows"].value == "1"
    assert fields["embedding_column"].value == "Present"
    assert fields["populated_embeddings"].value == "0 / 1"
    assert fields["vector_index"].value == "Missing"


def test_readiness_reports_fully_initialized_catalogue() -> None:
    engine = create_engine("sqlite://")
    _catalogue(engine, rows=True, embeddings=True, vector_index=True)

    report = _backend(engine).verify_readiness()
    fields = _fields(report)

    assert report.state.value == "ready"
    assert report.ready
    assert fields["populated_embeddings"].value == "1 / 1"
    assert fields["vector_index"].value == "Present"
    assert fields["embedding_model"].value == (
        "Configured model: comparator_embeddings"
    )


def test_readiness_does_not_pass_unsupported_timeout_to_ollama() -> None:
    engine = create_engine("sqlite://")
    _catalogue(engine, rows=True, embeddings=True, vector_index=True)
    probe_kwargs = None

    class AvailableOllamaModel:
        provider = "ollama"

        class Capabilities:
            embeddings = True

        capabilities = Capabilities()

        def is_available(self, **kwargs) -> bool:
            nonlocal probe_kwargs
            probe_kwargs = kwargs
            return True

    backend = PostgresComparatorSelectorBackend(
        engine,
        "main",
        model_backend_factory=AvailableOllamaModel,
        model_source="Configured model: comparator_embeddings",
    )

    report = backend.verify_readiness()

    assert report.state.value == "ready"
    assert probe_kwargs == {"allow_running_loop": True}


def test_readiness_reports_unreachable_database_without_leaking_url(
    tmp_path,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'missing' / 'catalogue.db'}")

    report = _backend(engine).verify_readiness()

    assert report.state.value == "error"
    assert _fields(report)["database_connection"].value == "Unavailable"
    assert "sqlite" not in repr(report).lower()


def test_embedding_creation_rejects_empty_source_before_model_use() -> None:
    engine = create_engine("sqlite://")
    _catalogue(engine, rows=False, embeddings=False, vector_index=False)
    model_used = False

    def model_factory():
        nonlocal model_used
        model_used = True
        return object()

    backend = PostgresComparatorSelectorBackend(
        engine,
        "main",
        model_backend_factory=model_factory,
    )

    with pytest.raises(RuntimeError, match="Load non-empty comparator"):
        backend.create_embedding_vectors()
    assert model_used is False


@pytest.mark.parametrize(
    ("vectors", "error"),
    [
        ([[0.5, 1.0], [1.0, 0.5]], None),
        ([[0.5, 1.0]], "Expected 2 embeddings, got 1"),
    ],
)
def test_embedding_creation_uses_omop_emb_without_a_shared_registry(
    monkeypatch, vectors, error
) -> None:
    engine = create_engine("sqlite://")
    # SQLite needs the pgvector reflection type to round-trip vector values.
    monkeypatch.setitem(engine.dialect.ischema_names, "HALFVEC", HALFVEC)
    ComparatorModels.create_catalogue_tables(engine, "main")
    models = ComparatorModels.reflect(engine, "main")
    with engine.begin() as connection:
        connection.execute(
            models.cohort_table.insert(),
            [
                {"cohort_definition_id": 2, "cohort_name": "Beta"},
                {"cohort_definition_id": 1, "cohort_name": "Alpha"},
            ],
        )
        connection.execute(
            models.similarity_table.insert(),
            {"cohort_definition_id_1": 1, "cohort_definition_id_2": 2},
        )
    model = Mock()
    model.embed_texts.return_value = vectors
    backend = PostgresComparatorSelectorBackend(
        engine, "main", model_backend_factory=lambda: model
    )

    if error is None:
        backend.create_embedding_vectors()
    else:
        with pytest.raises(RuntimeError, match=error):
            backend.create_embedding_vectors()

    model.embed_texts.assert_called_once_with(
        ["Alpha", "Beta"], role=EmbeddingRole.DOCUMENT, batch_size=None
    )
    with engine.connect() as connection:
        stored = connection.scalars(
            select(models.cohort_table.c.embedding_vector).order_by(
                models.cohort_table.c.cohort_definition_id
            )
        ).all()
    assert stored == (vectors if error is None else [None, None])
    assert inspect(engine).get_table_names() == ["cs_cohort", "cs_similarity"]
