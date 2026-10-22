"""Connections to the comparator catalogue and its embedding model."""

from collections.abc import Callable
from dataclasses import dataclass

from groundworkers.plugins import PluginReadinessResult
from oa_configurator import ResolvedDatabase
from omop_llm import ModelBackend

from comparator_recommender.backends import (
    ComparatorSelectorBackend,
    PostgresComparatorSelectorBackend,
)


@dataclass(frozen=True)
class ComparatorDataAdapter:
    """Own the database-backed comparator operations."""

    database: ResolvedDatabase
    backend: ComparatorSelectorBackend

    @classmethod
    def build(
        cls,
        database: ResolvedDatabase,
        model_backend_factory: Callable[[], ModelBackend] | None = None,
        model_source: str | None = None,
    ) -> "ComparatorDataAdapter":
        return cls(
            database=database,
            backend=PostgresComparatorSelectorBackend(
                engine=database.create_engine(register_claims=False),
                schema=database.schema_name or "public",
                model_backend_factory=model_backend_factory,
                model_source=model_source,
            ),
        )

    def find_target(self, name: str, top_n: int) -> list[tuple[int, str]]:
        return self.backend.find_target(name, top_n)

    def recommend_comparators(
        self, target_id: int, top_n: int, min_databases: int
    ) -> list[tuple[float, str]]:
        return self.backend.recommend_comparators(target_id, top_n, min_databases)

    def insert_data(self, cohort_table_path: str, similarity_table_path: str) -> None:
        self.backend.insert_data(cohort_table_path, similarity_table_path)

    def create_embedding_vectors(self) -> None:
        self.backend.create_embedding_vectors()

    def verify_readiness(self) -> PluginReadinessResult:
        """Return the backend's read-only readiness report."""

        return self.backend.verify_readiness()
