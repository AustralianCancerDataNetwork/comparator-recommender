"""Out-of-process setup commands launched by Groundworkers' setup console."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from pathlib import Path

from groundworkers.bootstrap import build_app_config
from oa_configurator import Resolver
from omop_llm import ModelBackend

from comparator_recommender.adapters import ComparatorDataAdapter
from comparator_recommender.config import ComparatorRecommenderConfig


def _adapter(config_path: str | None) -> ComparatorDataAdapter:
    app_config = build_app_config(config_path=config_path)
    plugin_config = ComparatorRecommenderConfig.validate_candidate(app_config.stack)
    resolver = Resolver(app_config.stack)
    database = resolver.resolve_database(plugin_config.comparator_db)
    model_factory: Callable[[], ModelBackend] | None = None
    if plugin_config.embedding_model_name is not None:
        resolved_model = resolver.resolve_model(plugin_config.embedding_model_name)

        def configured_model_factory() -> ModelBackend:
            from omop_llm import build_model_backend_from_resolved

            return build_model_backend_from_resolved(resolved_model)

        model_factory = configured_model_factory
    elif app_config.embedding_model is not None:
        resolved_model = app_config.embedding_model

        def configured_model_factory() -> ModelBackend:
            from omop_llm import build_model_backend_from_resolved

            return build_model_backend_from_resolved(resolved_model)

        model_factory = configured_model_factory

    model_source = (
        f"Configured model: {plugin_config.embedding_model_name}"
        if plugin_config.embedding_model_name is not None
        else (
            "Shared Groundworkers embedding model"
            if app_config.embedding_model is not None
            else None
        )
    )
    return ComparatorDataAdapter.build(
        database=database,
        model_backend_factory=model_factory,
        model_source=model_source,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Comparator Recommender setup")
    subparsers = parser.add_subparsers(dest="command", required=True)
    load = subparsers.add_parser("load-source")
    load.add_argument("--cohort-table", required=True, type=Path)
    load.add_argument("--similarity-table", required=True, type=Path)
    subparsers.add_parser("create-embeddings")
    args = parser.parse_args(argv)
    config_path = os.environ.get("OA_CONFIG_PATH")
    adapter = _adapter(config_path)
    if args.command == "load-source":
        adapter.insert_data(str(args.cohort_table), str(args.similarity_table))
    else:
        adapter.create_embedding_vectors()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
