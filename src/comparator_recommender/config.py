"""Configuration declared by the Comparator Recommender plugin."""

from typing import Annotated, ClassVar

from oa_configurator import GenericDatabaseConfig, ModelConfig, PackageConfigBase, RefTo
from pydantic import Field


class ComparatorRecommenderConfig(PackageConfigBase):
    """References and defaults for the comparator recommendation service."""

    tool_name: ClassVar[str] = "comparator_recommender"

    comparator_db: Annotated[str, RefTo(GenericDatabaseConfig)] = Field(
        default="comparator_db",
        description="Database containing the cohort and pairwise similarity tables.",
    )
    embedding_model_name: Annotated[str | None, RefTo(ModelConfig)] = Field(
        default=None,
        description=(
            "Optional model used to find target cohorts by semantic similarity. "
            "When unset, Groundworkers' shared embedding model is used."
        ),
    )
    min_databases_default: int = Field(
        default=1,
        ge=1,
        description="Default minimum number of databases supporting a recommendation.",
    )
