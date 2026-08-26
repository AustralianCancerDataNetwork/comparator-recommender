"""MCP tools exposed by the plugin."""

from typing import Any
import asyncio
from comparator_recommender.services import ComparatorRecommenderService


def register_tools(
    server: Any,
    service: ComparatorRecommenderService,
) -> None:
    """Register thin lookup and recommendation entry points."""

    @server.tool("comparator_recommender_find_target")
    async def comparator_recommender_find_target(
        name: str, top_n: int = 10
    ) -> dict[str, object]:
        """Find existing target cohorts by semantic similarity to a name."""
        matches = await asyncio.to_thread(service.find_target, name, top_n)
        return {
            "matches": [
                {"id": cohort_id, "name": cohort_name}
                for cohort_id, cohort_name in matches
            ]
        }

    @server.tool("comparator_recommender_recommend")
    def comparator_recommender_recommend(
        target_id: int,
        top_n: int = 10,
        min_databases: int | None = None,
    ) -> dict[str, object]:
        """Recommend pairwise comparators for an existing target cohort."""
        recommendations = service.recommend_comparators(target_id, top_n, min_databases)
        return {
            "recommendations": [
                {"similarity": round(score, 3), "name": name}
                for score, name in recommendations
            ]
        }

    @server.tool("comparator_recommender_status")
    def comparator_recommender_status() -> dict[str, object]:
        """Return the same read-only readiness report used by the TUI."""

        return service.verify_readiness().as_dict()
