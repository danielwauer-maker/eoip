from __future__ import annotations

import os
from pathlib import Path

import pytest

from eoip.config import load_company_profile, load_generator_config
from eoip.database import (
    apply_migrations,
    connect_database,
    load_dataset,
    refresh_dimensional_model,
)
from eoip.executive_reporting import (
    load_executive_spec,
    validate_executive_database,
    validate_executive_spec,
)
from eoip.generator import ERPGenerator
from eoip.semantic import load_kpi_catalog


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "semantic" / "kpi-catalog.yaml"
EXECUTIVE_SPEC = ROOT / "powerbi" / "executive-overview.yaml"
DATABASE_URL = os.environ.get("EOIP_TEST_DATABASE_URL")


def test_executive_overview_contract():
    catalog = load_kpi_catalog(CATALOG)
    page = load_executive_spec(EXECUTIVE_SPEC)

    result = validate_executive_spec(page, catalog)
    assert result["passed"], result


@pytest.mark.skipif(not DATABASE_URL, reason="EOIP_TEST_DATABASE_URL is not configured")
def test_executive_overview_reference_views():
    company = load_company_profile(ROOT / "tests" / "fixtures" / "company.yaml")
    config = load_generator_config(ROOT / "config" / "generator.yaml")
    dataset = ERPGenerator(company, config, scale_factor=0.002).generate()

    with connect_database(DATABASE_URL) as connection:
        migrations = apply_migrations(connection)
        assert "060_executive_overview_views.sql" in migrations

        load_dataset(connection, dataset, truncate=True)
        refresh_dimensional_model(connection)

        result = validate_executive_database(connection)
        assert result["passed"], result

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM semantic.v_executive_category_reference
                WHERE stockout_risk_sku_count > 0
                """
            )
            assert int(cursor.fetchone()[0]) > 0
