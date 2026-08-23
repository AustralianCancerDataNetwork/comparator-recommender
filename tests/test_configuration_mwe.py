"""End-to-end MWE for the host-provided generic configuration workflow."""

from pathlib import Path

from groundskeeping.configurator import ConfigWizardController, MutationOperation
from groundskeeping.contracts import ReviewStep
from groundworkers.application.setup.plugin_configuration import (
    PackageConfigMutationService,
)
from groundworkers.plugins import (
    PluginConfigResolver,
    PluginContext,
    validate_plugin_identities,
)
from oa_configurator import (
    CDMDatabaseConfig,
    ConnectionConfig,
    Resolver,
    StackConfig,
    load_stack_config_from_path,
    save_stack_config,
)

from comparator_recommender import ComparatorRecommenderConfig, plugin


def _write_minimal_stack(path: Path) -> None:
    stack = StackConfig(
        connections={
            "cdm_main": ConnectionConfig(
                dialect="sqlite",
                database_name=":memory:",
            )
        },
        databases={
            "cdm_db": CDMDatabaseConfig(
                connection="cdm_main",
                schema_name="main",
                vocab_schema="main",
            )
        },
    )
    save_stack_config(stack, path)


def test_plugin_identity_matches_oa_configuration_identity() -> None:
    validate_plugin_identities([plugin])
    assert plugin.name == ComparatorRecommenderConfig.tool_name


def test_plugin_composes_adapter_service_and_diagnostic_tool() -> None:
    stack = StackConfig(
        connections={
            "cdm_main": ConnectionConfig(
                dialect="sqlite",
                database_name=":memory:",
            )
        },
        databases={
            "cdm_db": CDMDatabaseConfig(
                connection="cdm_main",
                schema_name="main",
                vocab_schema="main",
            )
        },
    )
    context = PluginContext(
        resolver=PluginConfigResolver(Resolver(stack)),
        cdm_database=None,
        cdm_engine=None,
        vector_store=None,
        embedding_backend_factory=None,
        embedding_model_backend_factory=None,
        chat_backend_factory=None,
    )
    state = plugin.build(
        context,
        ComparatorRecommenderConfig(comparator_db="cdm_db"),
    )
    assert state is not None
    assert state.service.comparator_data.database.name == "cdm_db"

    class FakeServer:
        def __init__(self):
            self.tools = {}

        def tool(self, name):
            def register(function):
                self.tools[name] = function
                return function

            return register

    server = FakeServer()
    plugin.register(server, state)
    assert server.tools["comparator_recommender_status"]() == {
        "configured": True,
        "comparator_db": "cdm_db",
        "embedding_model_name": None,
        "vector_store_name": None,
        "min_databases_default": 2,
        "recommendation_functionality": False,
    }


def test_installed_plugin_contributes_a_generic_setup_page(tmp_path: Path) -> None:
    from groundworkers.tui.app import build_groundworkers_tui_spec

    path = tmp_path / "config.toml"
    _write_minimal_stack(path)

    spec = build_groundworkers_tui_spec(config_path=str(path))

    assert spec.validate().keys() == ("setup", "plugin.comparator_recommender")


def test_generic_provider_writes_comparator_recommender_configuration(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    _write_minimal_stack(path)
    service = PackageConfigMutationService(path, ComparatorRecommenderConfig)
    workflow = service.workflow(MutationOperation.UPDATE)
    controller = ConfigWizardController(workflow, service)

    snapshot = controller.start()
    assert snapshot.step.key == "comparator_db"
    snapshot = controller.submit({"comparator_db": "cdm_db"}).snapshot
    snapshot = controller.submit(
        {"embedding_model_name": "__not_configured__"}
    ).snapshot
    snapshot = controller.submit({"vector_store_name": "__not_configured__"}).snapshot
    snapshot = controller.submit({"min_databases_default": 3}).snapshot

    assert isinstance(snapshot.step, ReviewStep)
    assert snapshot.can_apply
    assert controller.apply().applied

    saved = load_stack_config_from_path(path)
    configured = ComparatorRecommenderConfig.validate_candidate(saved)
    assert saved.tools["comparator_recommender"] == {
        "comparator_db": "cdm_db",
        "min_databases_default": 3,
    }
    assert configured == ComparatorRecommenderConfig(
        comparator_db="cdm_db",
        embedding_model_name=None,
        vector_store_name=None,
        min_databases_default=3,
    )
