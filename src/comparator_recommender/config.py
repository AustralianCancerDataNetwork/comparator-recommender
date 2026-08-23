"""Configuration declared by the Comparator Recommender plugin."""

from typing import Annotated, ClassVar

from oa_configurator import (
    CDMDatabaseConfig,
    ModelConfig,
    PackageConfigBase,
    RefTo,
    VectorStoreConfig,
)
from pydantic import Field


class ComparatorRecommenderConfig(PackageConfigBase):
    """References and defaults needed by a future recommender service."""

    tool_name: ClassVar[str] = "comparator_recommender"

    comparator_db: Annotated[str, RefTo(CDMDatabaseConfig)] = Field(
        default="cdm_db",
        description="CDM database containing candidate comparator cohorts.",
    )
    embedding_model_name: Annotated[str | None, RefTo(ModelConfig)] = Field(
        default=None,
        description="Optional embedding model for future semantic ranking.",
    )
    vector_store_name: Annotated[str | None, RefTo(VectorStoreConfig)] = Field(
        default=None,
        description="Optional vector store for future semantic ranking.",
    )
    min_databases_default: int = Field(
        default=2,
        ge=1,
        description="Minimum database count a future recommender should require.",
    )
