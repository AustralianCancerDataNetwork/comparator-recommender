"""Serving must not write schema provenance: attendee logins are read-only."""

from types import SimpleNamespace

from sqlalchemy import create_engine

from comparator_recommender.adapters import ComparatorDataAdapter


def test_build_checks_schema_claims_without_registering_them() -> None:
    """Registering claims UPDATEs the provenance registry, which a read-only login cannot do."""
    calls = []

    def fake_create_engine(**kwargs):
        calls.append(kwargs)
        return create_engine("sqlite://")

    database = SimpleNamespace(create_engine=fake_create_engine, schema_name="comparator")
    adapter = ComparatorDataAdapter.build(database=database)

    assert calls == [{"register_claims": False}]
    assert adapter.backend.schema == "comparator"
