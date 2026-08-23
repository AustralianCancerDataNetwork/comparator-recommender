"""Connections to databases and other external systems.

An adapter is the boundary between this plugin and something outside it. In this
case that will be an OMOP database. Keeping database code here prevents SQL and
connection details from spreading into the recommendation rules.
"""

from dataclasses import dataclass

from oa_configurator import ResolvedDatabase


@dataclass(frozen=True)
class ComparatorDataAdapter:
    """The database details needed by future comparator queries."""

    database: ResolvedDatabase

    # ADAPTER EXTENSION POINT:
    
    # Add methods that read comparator data here. This is also where you would
    # create/use a SQLAlchemy engine from ``database.connection``. Return plain
    # Python objects from those methods so the service layer does not need to
    # know about SQL, schemas, or connection strings.
