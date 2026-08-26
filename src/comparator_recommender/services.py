"""Comparator Recommender business logic."""

from dataclasses import dataclass

from groundworkers.plugins import (
    PluginReadinessField,
    PluginReadinessResult,
    PluginReadinessState,
)

from comparator_recommender.adapters import ComparatorDataAdapter


@dataclass(frozen=True)
class ComparatorRecommenderService:
    """Validate request policy before delegating to the catalogue adapter."""

    comparator_data: ComparatorDataAdapter
    min_databases_default: int = 1

    def verify_readiness(self) -> PluginReadinessResult:
        """Return the catalogue adapter's read-only readiness report."""

        report = self.comparator_data.verify_readiness()
        configuration = (
            PluginReadinessField(
                "comparator_database",
                "Comparator database",
                self.comparator_data.database.name,
                PluginReadinessState.READY,
                "Logical database reference from plugin configuration.",
            ),
            PluginReadinessField(
                "min_databases_default",
                "Recommendation minimum databases",
                str(self.min_databases_default),
                PluginReadinessState.READY,
                "Default evidence threshold for comparator recommendations.",
            ),
        )
        return PluginReadinessResult(
            state=report.state,
            summary=report.summary,
            fields=(*configuration, *report.fields),
            configured=report.configured,
        )

    def find_target(self, name: str, top_n: int = 10) -> list[tuple[int, str]]:
        if not name.strip():
            raise ValueError("name must be a non-empty string")
        return self.comparator_data.find_target(name, _limit(top_n))

    def recommend_comparators(
        self,
        target_id: int,
        top_n: int = 10,
        min_databases: int | None = None,
    ) -> list[tuple[float, str]]:
        if target_id <= 0:
            raise ValueError("target_id must be a positive integer")
        resolved_min_databases = (
            self.min_databases_default if min_databases is None else min_databases
        )
        if resolved_min_databases < 1:
            raise ValueError("min_databases must be at least 1")
        return self.comparator_data.recommend_comparators(
            target_id, _limit(top_n), resolved_min_databases
        )


def _limit(value: int) -> int:
    if value <= 0:
        raise ValueError("top_n must be a positive integer")
    return min(value, 100)
