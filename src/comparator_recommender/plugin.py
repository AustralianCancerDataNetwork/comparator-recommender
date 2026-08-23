"""Minimal Groundworkers plugin shell.

The package intentionally stops at configuration and registration. The status
tool proves that the installed plugin received its validated configuration; it is
not comparator-recommendation functionality.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from groundworkers.plugins import PluginContext
from oa_configurator import PackageConfigBase

from comparator_recommender.adapters import ComparatorDataAdapter
from comparator_recommender.config import ComparatorRecommenderConfig
from comparator_recommender.services import ComparatorRecommenderService
from comparator_recommender.tools import register_tools


@dataclass(frozen=True)
class ComparatorRecommenderState:
    """Objects built once and then shared by all of this plugin's tools."""

    config: ComparatorRecommenderConfig
    service: ComparatorRecommenderService


class ComparatorRecommenderPlugin:
    """Configuration-only implementation of the Groundworkers plugin contract."""

    name = "comparator_recommender"
    config_cls: ClassVar[type[PackageConfigBase] | None] = ComparatorRecommenderConfig

    def build(
        self,
        context: PluginContext,
        config: PackageConfigBase | None,
    ) -> ComparatorRecommenderState | None:
        """Connect configuration, adapters, and services at application startup."""

        if not isinstance(config, ComparatorRecommenderConfig):
            return None

        # BUILD/COMPOSITION ONLY:
        # ``build`` joins the layers together; it should not contain SQL or
        # recommendation rules. Resolve any additional configured connections,
        # construct their adapters, and then give those adapters to services.

        comparator_database = context.resolver.resolve_database(config.comparator_db)
        comparator_data = ComparatorDataAdapter(database=comparator_database)
        service = ComparatorRecommenderService(
            comparator_data=comparator_data
        )
        return ComparatorRecommenderState(config=config, service=service)

    def register(self, server: Any, state: object) -> None:
        """Register a diagnostic tool proving configuration reached the plugin."""

        if not isinstance(state, ComparatorRecommenderState):
            raise TypeError("Comparator Recommender received invalid plugin state.")

        # REGISTRATION ONLY:

        # Keep the tool definitions in tools.py. This method only hands the MCP
        # server and the already-built service to that registration function.

        register_tools(server, state.config, state.service)


plugin = ComparatorRecommenderPlugin()
