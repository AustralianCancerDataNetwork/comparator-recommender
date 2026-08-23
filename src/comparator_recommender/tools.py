"""MCP tools exposed by the plugin.

Tools are thin entry points. They translate an MCP request into a service call
and return the result. The lookup/ranking/recommendation rules do not belong in
this module.
"""

from typing import Any

from comparator_recommender.config import ComparatorRecommenderConfig
from comparator_recommender.services import ComparatorRecommenderService


def register_tools(
    server: Any,
    config: ComparatorRecommenderConfig,
    service: ComparatorRecommenderService,
) -> None:
    """Register this plugin's tools with the Groundworkers MCP server."""

    # TOOL EXTENSION POINT:

    # Add new ``@server.tool(...)`` functions here. Each function should do as
    # little as possible: check/describe its inputs, call one service method,
    # and return the service result in a useful shape.
    
    @server.tool("comparator_recommender_status")
    def comparator_recommender_status() -> dict[str, object]:
        """Confirm that the scaffold received its validated configuration."""

        return {
            "configured": True,
            "comparator_db": service.comparator_data.database.name,
            "embedding_model_name": config.embedding_model_name,
            "vector_store_name": config.vector_store_name,
            "recommendation_functionality": False,
        }
