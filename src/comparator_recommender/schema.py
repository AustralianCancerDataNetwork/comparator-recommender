"""SQLAlchemy schema for this plugin's own cohort/comparator tables.

``cs_cohorts``/``cs_similarity`` are comparator-recommender's own tables 
and living wherever ``comparator_db`` resolves to (see config.py). 

This is a separate declarative base from any OMOP CDM mapping (? does it
have to be) same physical database is fine (a different schema, via 
``comparator_db.schema_name``), but a shared base would imply a
shared table namespace this plugin does not own.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# not using orm-loader base classes because it feels like overkill but 
# maybe we will down the line?
class Base(DeclarativeBase): 
    """Declarative base for comparator-recommender's own tables only."""


class CsCohort(Base):
    """One candidate cohort, downloaded from the OHDSI comparator payload."""

    __tablename__ = "cs_cohorts"

    cohort_id: Mapped[int] = mapped_column(primary_key=True)
    cohort_name: Mapped[str]
    n_databases: Mapped[int]


class CsSimilarity(Base):
    """One target/comparator pairing and the network overlap behind it."""

    __tablename__ = "cs_similarity"

    target_cohort_id: Mapped[int] = mapped_column(
        ForeignKey("cs_cohorts.cohort_id"), primary_key=True
    )
    comparator_cohort_id: Mapped[int] = mapped_column(
        ForeignKey("cs_cohorts.cohort_id"), primary_key=True
    )
    n_databases: Mapped[int]
