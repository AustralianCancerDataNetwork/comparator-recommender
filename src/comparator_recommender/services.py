"""Comparator Recommender business logic.

A service combines data from adapters and applies the rules of the use case. It
should not know about MCP tool decorators or how configuration is stored.
"""

from dataclasses import dataclass

from comparator_recommender.adapters import ComparatorDataAdapter


@dataclass(frozen=True)
class ComparatorRecommenderService:
    """Dependencies and settings for future recommendation operations."""

    comparator_data: ComparatorDataAdapter

    # SERVICE EXTENSION POINT:

    # Add the core use-case methods here, for example:
    #   - look up possible comparator cohorts through ``comparator_data``;
    #   - rank those candidates;
    #   - return a recommendation with the evidence used to produce it.
    
    # Keep database queries in the adapter and MCP request/response formatting
    # in tools.py.
