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
    GenericDatabaseConfig,
    Resolver,
    StackConfig,
    load_stack_config,
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
            ),
            "comparator_db": GenericDatabaseConfig(
                connection="cdm_main",
            ),
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
            ),
            "comparator_db": GenericDatabaseConfig(
                connection="cdm_main",
            ),
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
        ComparatorRecommenderConfig(comparator_db="comparator_db"),
    )
    assert state is not None
    assert state.service.comparator_data.database.name == "comparator_db"

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
    status = server.tools["comparator_recommender_status"]()
    assert status == state.service.verify_readiness().as_dict()
    assert status["state"] == "warning"
    assert status["configured"] is True
    assert status["ready"] is False
    assert {field["key"] for field in status["fields"]} >= {
        "database_connection",
        "cohort_table",
        "similarity_table",
        "embedding_model",
    }


def test_installed_plugin_contributes_a_generic_setup_page(tmp_path: Path) -> None:
    from groundworkers.tui.app import build_groundworkers_tui_spec

    path = tmp_path / "config.toml"
    _write_minimal_stack(path)

    spec = build_groundworkers_tui_spec(config_path=str(path))

    assert spec.validate().keys() == (
        "setup",
        "gw_plugin-comparator_recommender",
        "comparator_recommender_load_source",
        "comparator_recommender_create_embeddings",
    )
    page = spec.pages[1].factory(None)
    view = page.landing_view(None)
    assert view.status.value == "warning"
    assert tuple(action.label for action in view.actions) == ("Configure", "Verify")
    assert {row.key for row in view.rows} >= {
        "database_connection",
        "cohort_table",
        "cohort_rows",
        "embedding_column",
        "populated_embeddings",
        "vector_index",
        "embedding_model",
    }


def test_setup_steps_build_durable_commands(tmp_path: Path) -> None:
    cohort = tmp_path / "cohort.csv"
    similarity = tmp_path / "similarity.csv"
    cohort.touch()
    similarity.touch()

    load_step, embedding_step = plugin.setup_steps
    plan = load_step.build_plan(
        {
            "cohort_table_path": cohort,
            "similarity_table_path": similarity,
        },
        str(tmp_path / "config.toml"),
    )
    assert plan.kind == "comparator-recommender-load-source"
    assert "comparator_recommender.setup_cli" in plan.steps[0].command.argv
    assert str(cohort) in plan.steps[0].command.argv
    assert embedding_step.build_plan({}, str(tmp_path / "config.toml")).kind == (
        "comparator-recommender-create-embeddings"
    )


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
    snapshot = controller.submit({"comparator_db": "comparator_db"}).snapshot
    snapshot = controller.submit(
        {"embedding_model_name": "__not_configured__"}
    ).snapshot
    snapshot = controller.submit({"min_databases_default": 3}).snapshot

    assert isinstance(snapshot.step, ReviewStep)
    assert snapshot.can_apply
    assert controller.apply().applied

    saved = load_stack_config(path)
    configured = ComparatorRecommenderConfig.validate_candidate(saved)
    assert saved.tools["comparator_recommender"] == {
        "comparator_db": "comparator_db",
        "min_databases_default": 3,
    }
    assert configured == ComparatorRecommenderConfig(
        comparator_db="comparator_db",
        embedding_model_name=None,
        min_databases_default=3,
    )
