"""SQLAlchemy mappings for the non-OMOP comparator catalogue tables.

These tables are not part of the OMOP CDM, so they do not belong in
``omop-alchemy``. They are nevertheless mapped with the same declarative
principles: schema-qualified tables, explicit primary-key hints, and normal
SQLAlchemy expressions for reads and updates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import BigInteger, MetaData, PrimaryKeyConstraint, Table, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import registry


@dataclass(frozen=True)
class ComparatorModels:
    """Reflected ORM classes for one configured comparator schema."""

    cohort: type[Any]
    similarity: type[Any]
    cohort_table: Table
    similarity_table: Table

    @classmethod
    def reflect(cls, engine: Engine, schema: str) -> ComparatorModels:
        metadata = MetaData()
        cohort_table = Table("cs_cohort", metadata, schema=schema, autoload_with=engine)
        similarity_table = Table("cs_similarity", metadata, schema=schema, autoload_with=engine)

        # CSV imports may not carry primary-key constraints. SQLAlchemy ORM
        # still needs identity keys for mapped classes, so apply the natural
        # keys to the reflected tables.
        _ensure_primary_key(cohort_table, "cohort_definition_id")
        _ensure_primary_key(
            similarity_table,
            "cohort_definition_id_1",
            "cohort_definition_id_2",
        )

        mapper_registry = registry()

        class Cohort:
            pass

        class Similarity:
            pass

        mapper_registry.map_imperatively(Cohort, cohort_table)
        mapper_registry.map_imperatively(Similarity, similarity_table)
        return cls(Cohort, Similarity, cohort_table, similarity_table)

    @classmethod
    def create_catalogue_tables(cls, engine: Engine, schema: str) -> None:
        """Create the catalogue shape used by the CSV import path.

        Existing tables are left untouched. This does not silently migrate an
        old table that lacks ``embedding_vector``; that is an explicit schema
        migration decision.
        """
        from sqlalchemy import Column, Float, Integer, String

        metadata = MetaData()
        Table(
            "cs_cohort", metadata,
            # OMOP cohort identifiers are BIGINT-sized in the source data.
            Column("cohort_definition_id", BigInteger, primary_key=True),
            Column("cohort_name", String, nullable=True),
            Column("database_count", Integer),
            Column("embedding_vector", HALFVEC(), nullable=True),
            schema=schema,
        )
        Table(
            "cs_similarity", metadata,
            Column("cohort_definition_id_1", BigInteger, primary_key=True),
            Column("cohort_definition_id_2", BigInteger, primary_key=True),
            Column("mean_cosine_similarity", Float), Column("database_count", Integer),
            schema=schema,
        )
        metadata.create_all(engine)


def _ensure_primary_key(table: Table, *column_names: str) -> None:
    if table.primary_key.columns:
        return
    columns = [table.c.get(column_name) for column_name in column_names]
    if any(column is None for column in columns):
        missing = [name for name, column in zip(column_names, columns, strict=True) if column is None]
        raise RuntimeError(f"{table.fullname} is missing required columns: {', '.join(missing)}")
    table.append_constraint(PrimaryKeyConstraint(*column_names))


def has_column(engine: Engine, schema: str, table: str, column: str) -> bool:
    return any(item["name"] == column for item in inspect(engine).get_columns(table, schema=schema))
