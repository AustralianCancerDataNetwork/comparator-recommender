"""Storage-independent comparator backend contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from groundworkers.plugins import PluginReadinessResult
from omop_llm import ModelBackend
from sqlalchemy import Engine


class ComparatorSelectorBackend(ABC):
    """Operations required by the comparator recommender service."""

    def __init__(
        self,
        engine: Engine,
        schema: str,
        model_backend_factory: Callable[[], ModelBackend] | None = None,
        model_source: str | None = None,
    ) -> None:
        if not schema.strip():
            raise ValueError("schema must not be empty")
        self.engine = engine
        self.schema = schema
        self.model_backend_factory = model_backend_factory
        self.model_source = model_source

    def pre_initialise_store(self) -> None:
        """Prepare mutating setup prerequisites; the default is a no-op.

        Backend construction and readiness checks are deliberately read-only.
        Mutating setup operations call this hook explicitly when needed.
        """

    @abstractmethod
    def find_target(self, name: str, top_n: int) -> list[tuple[int, str]]: ...

    @abstractmethod
    def recommend_comparators(
        self, target_id: int, top_n: int, min_databases: int
    ) -> list[tuple[float, str]]: ...

    @abstractmethod
    def insert_data(
        self, cohort_table_path: str, similarity_table_path: str
    ) -> None: ...

    @abstractmethod
    def create_embedding_vectors(self) -> None: ...

    @abstractmethod
    def verify_readiness(self) -> PluginReadinessResult: ...
