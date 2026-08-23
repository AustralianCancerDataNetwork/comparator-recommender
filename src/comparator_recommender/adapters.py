"""Connections to databases and other external systems.

An adapter is the boundary between this plugin and something outside it. In this
case that will be a database holding this plugin's own cs_cohorts/cs_similarity
tables (see schema.py). Keeping database code here prevents SQL and connection
details from spreading into the recommendation rules.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from oa_configurator import ResolvedDatabase
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from comparator_recommender.schema import CsCohort, CsSimilarity


@dataclass(frozen=True)
class ComparatorDataAdapter:
    """Comparator data access, always through schema.py's mapped classes.

    ``select()``/``Session.get()`` against ``CsCohort``/``CsSimilarity``,
    never ``text()`` or a raw connection.
    """

    database: ResolvedDatabase
    engine: Engine = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        # schema_translate_map from ResolvedDatabase.create_engine keeps
        # cs_cohorts/cs_similarity in whatever schema comparator_db names,
        # not just the connection's default.
        object.__setattr__(self, "engine", self.database.create_engine(future=True))

    def _session(self) -> Session:
        return Session(self.engine)

    # ADAPTER EXTENSION POINT:
    #
    # Add further read methods here in the same shape as the two below:
    # build a `select(...)`, run it inside `with self._session() as session:`,
    # and return plain Python objects (or mapped instances). 
    # 
    # `find_target_cohort`'s embedding search still needs an
    # embedding backend wired in separately; these two cover the
    # deterministic half of `suggest_comparators`.

    def get_cohort(self, cohort_id: int) -> CsCohort | None:
        """Look up one candidate cohort by id."""

        with self._session() as session:
            return session.get(CsCohort, cohort_id)

    def list_comparators(
        self, target_cohort_id: int, *, min_databases: int
    ) -> Sequence[CsSimilarity]:
        """List comparator pairings meeting the minimum network overlap."""

        statement = select(CsSimilarity).where(
            CsSimilarity.target_cohort_id == target_cohort_id,
            CsSimilarity.n_databases >= min_databases,
        )
        with self._session() as session:
            return session.scalars(statement).all()
