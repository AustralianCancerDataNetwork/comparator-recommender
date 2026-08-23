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

    # CONFIGURATION EXTENSION POINT:
    # do we assume that the comparator database is always separate from the CDM database? 
    # probably yes and therefore there should be a distinct config for it. Probably need 
    # to work through exactly what you expect as the first step in building this out...
    # as defined below the comparator database is optional and defaults to the CDM database, 
    # but that may not be the right approach.

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
