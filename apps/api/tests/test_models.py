"""Model metadata tests — no database required.

Importing the models and configuring mappers validates every relationship
annotation across the model modules.
"""

from sqlalchemy import Uuid
from sqlalchemy.orm import configure_mappers

from app.models import Base

EXPECTED_TABLES = {
    "users",
    "training_centres",
    "provider_staff",
    "courses",
    "trainees",
    "consents",
    "employers",
    "employment_records",
    "followups",
    "verifications",
    "market_demand",
    "provider_scores",
    "fund_allocations",
    "events",
    "notifications",
    "contact_messages",
    "push_subscriptions",
}


def test_metadata_contains_all_domain_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_every_table_has_uuid_pk_and_timestamps() -> None:
    for table in Base.metadata.tables.values():
        assert table.primary_key.columns.keys() == ["id"], table.name
        assert isinstance(table.c.id.type, Uuid), table.name
        assert {"created_at", "updated_at"} <= set(table.c.keys()), table.name


def test_mapper_configuration_resolves_all_relationships() -> None:
    configure_mappers()
