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

from comparator_recommender.config import ComparatorRecommenderConfig


@dataclass(frozen=True)
class ComparatorRecommenderState:
    """Validated configuration retained by the MWE plugin."""

    config: ComparatorRecommenderConfig


class ComparatorRecommenderPlugin:
    """Configuration-only implementation of the Groundworkers plugin contract."""

    name = "comparator_recommender"
    config_cls: ClassVar[type[PackageConfigBase] | None] = ComparatorRecommenderConfig

    def build(
        self,
        context: PluginContext,
        config: PackageConfigBase | None,
    ) -> ComparatorRecommenderState | None:
        """Accept the host-validated configuration without building a recommender."""

        del context
        if not isinstance(config, ComparatorRecommenderConfig):
            return None
        return ComparatorRecommenderState(config=config)

    def register(self, server: Any, state: object) -> None:
        """Register a diagnostic tool proving configuration reached the plugin."""

        if not isinstance(state, ComparatorRecommenderState):
            raise TypeError("Comparator Recommender received invalid plugin state.")

        @server.tool("comparator_recommender_status")
        def comparator_recommender_status() -> dict[str, object]:
            return {
                "configured": True,
                "comparator_db": state.config.comparator_db,
                "embedding_model_name": state.config.embedding_model_name,
                "vector_store_name": state.config.vector_store_name,
                "min_databases_default": state.config.min_databases_default,
                "recommendation_functionality": False,
            }


plugin = ComparatorRecommenderPlugin()
