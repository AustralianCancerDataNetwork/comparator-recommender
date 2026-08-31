"""Groundworkers composition root for comparator recommendation."""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from groundworkers.application.setup.maintenance_runs import (
    Command,
    CommandPlan,
    CommandStep,
)
from groundworkers.plugins import (
    PluginContext,
    PluginReadinessResult,
    PluginSetupArgument,
    PluginSetupStep,
)
from oa_configurator import PackageConfigBase
from omop_llm import ModelBackend

from comparator_recommender.adapters import ComparatorDataAdapter
from comparator_recommender.config import ComparatorRecommenderConfig
from comparator_recommender.services import ComparatorRecommenderService
from comparator_recommender.tools import register_tools


def _setup_command(
    command: str,
    arguments: tuple[str, ...],
    config_path: str,
) -> Command:
    return Command(
        argv=(
            sys.executable,
            "-m",
            "comparator_recommender.setup_cli",
            command,
            *arguments,
        ),
        environment=(("OA_CONFIG_PATH", config_path),),
    )


def _load_source_plan(
    values: Mapping[str, object], config_path: str
) -> CommandPlan:
    cohort_path = str(values["cohort_table_path"])
    similarity_path = str(values["similarity_table_path"])
    return CommandPlan(
        kind="comparator-recommender-load-source",
        steps=(
            CommandStep(
                key="load-comparator-source",
                command=_setup_command(
                    "load-source",
                    (
                        "--cohort-table",
                        cohort_path,
                        "--similarity-table",
                        similarity_path,
                    ),
                    config_path,
                ),
                affected_resources=(f"comparator:{config_path}",),
            ),
        ),
        affected_resources=(f"comparator:{config_path}",),
    )


def _embedding_plan(_values: Mapping[str, object], config_path: str) -> CommandPlan:
    return CommandPlan(
        kind="comparator-recommender-create-embeddings",
        steps=(
            CommandStep(
                key="create-comparator-embeddings",
                command=_setup_command("create-embeddings", (), config_path),
                affected_resources=(f"comparator:{config_path}",),
            ),
        ),
        affected_resources=(f"comparator:{config_path}",),
    )


@dataclass(frozen=True)
class ComparatorRecommenderState:
    """Objects built once and then shared by all of this plugin's tools."""

    config: ComparatorRecommenderConfig
    service: ComparatorRecommenderService


class ComparatorRecommenderPlugin:
    """Implementation of the Groundworkers plugin contract."""

    name = "comparator_recommender"
    config_cls: ClassVar[type[PackageConfigBase] | None] = ComparatorRecommenderConfig
    setup_steps = (
        PluginSetupStep(
            key="comparator_recommender_load_source",
            title="Load comparator source",
            purpose=(
                "Load cohort and pairwise similarity CSVs into the comparator "
                "catalogue. After the run succeeds, return to Comparator "
                "Recommender and select Verify to see the updated status."
            ),
            arguments=(
                PluginSetupArgument(
                    "cohort_table_path",
                    "Cohort table CSV",
                    kind="existing_path",
                    help="The cohort summary CSV produced by the comparator pipeline.",
                ),
                PluginSetupArgument(
                    "similarity_table_path",
                    "Similarity table CSV",
                    kind="existing_path",
                    help="The pairwise similarity CSV produced by the comparator pipeline.",
                ),
            ),
            build_plan=_load_source_plan,
        ),
        PluginSetupStep(
            key="comparator_recommender_create_embeddings",
            title="Create comparator embeddings",
            purpose=(
                "Generate and store semantic vectors for the loaded comparator "
                "catalogue. A successful non-empty source load must complete first; "
                "the run fails safely otherwise. After the run succeeds, return to "
                "Comparator Recommender and select Verify."
            ),
            arguments=(),
            build_plan=_embedding_plan,
        ),
    )

    def build(
        self,
        context: PluginContext,
        config: PackageConfigBase | None,
    ) -> ComparatorRecommenderState | None:
        """Connect configuration, adapters, and services at application startup."""

        if not isinstance(config, ComparatorRecommenderConfig):
            return None

        comparator_database = context.resolver.resolve_database(config.comparator_db)
        model_backend_factory: Callable[[], ModelBackend] | None = (
            context.embedding_model_backend_factory
        )
        model_source = (
            "Shared Groundworkers embedding model"
            if model_backend_factory is not None
            else None
        )
        if config.embedding_model_name is not None:
            resolved_model = context.resolver.resolve_model(config.embedding_model_name)
            model_source = f"Configured model: {config.embedding_model_name}"

            def configured_model_backend_factory() -> ModelBackend:
                from omop_llm import build_model_backend_from_resolved

                return build_model_backend_from_resolved(resolved_model)

            model_backend_factory = configured_model_backend_factory

        comparator_data = ComparatorDataAdapter.build(
            database=comparator_database,
            model_backend_factory=model_backend_factory,
            model_source=model_source,
        )
        service = ComparatorRecommenderService(
            comparator_data=comparator_data,
            min_databases_default=config.min_databases_default,
        )
        return ComparatorRecommenderState(config=config, service=service)

    def register(self, server: Any, state: object) -> None:
        """Register the plugin's tools against the shared guarded server."""

        if not isinstance(state, ComparatorRecommenderState):
            raise TypeError("Comparator Recommender received invalid plugin state.")

        register_tools(server, state.service)

    def verify_readiness(self, state: object) -> PluginReadinessResult:
        """Return comparator-specific readiness through the host contract."""

        if not isinstance(state, ComparatorRecommenderState):
            raise TypeError("Comparator Recommender received invalid plugin state.")
        return state.service.verify_readiness()


plugin = ComparatorRecommenderPlugin()
