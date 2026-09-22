from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_pre_render_visual_qa_contract():
    executive = load_yaml(ROOT / "powerbi" / "executive-overview.yaml")["page"]
    sales = load_yaml(ROOT / "powerbi" / "report-pages.yaml")["report"]
    inventory = load_yaml(ROOT / "powerbi" / "inventory-intelligence.yaml")["report"]
    design = load_yaml(ROOT / "powerbi" / "visual-design-system.yaml")[
        "visual_design_system"
    ]
    dax = (ROOT / "powerbi" / "measures.dax").read_text(encoding="utf-8")

    assert design["status"] == "pre_render_qa_approved"
    assert design["semantic_context"]["inventory_measures"]["date_behavior"].startswith(
        "latest snapshot"
    )

    assert "semantic_context" in executive
    assert "selected period" in executive["semantic_context"]["visible_context_note"]
    assert "latest snapshot" in executive["semantic_context"]["visible_context_note"]

    assert "REMOVEFILTERS('dim_date')" in dax

    margin_page = next(
        page for page in sales["pages"] if page["id"] == "margin_discount"
    )
    attention = next(
        visual
        for visual in margin_page["visuals"]
        if visual["id"] == "margin_exception_table"
    )
    assert attention["rows"] == ["dim_customer.customer_name"]
    assert attention["validation_filter"] == {
        "field": "entity_type",
        "equals": "customer",
    }
    assert attention["top_n"] <= 12

    customer_product = next(
        page for page in sales["pages"] if page["id"] == "customer_product"
    )
    rank_visuals = [
        visual
        for visual in customer_product["visuals"]
        if visual["id"] in {"cp_customer_rank", "cp_product_rank"}
    ]
    assert all(visual["top_n"] <= 10 for visual in rank_visuals)

    assert "snapshot_context" in inventory
    assert all(
        item["id"] != "date_range" for item in inventory.get("page_filters", [])
    )
    risk_page = next(
        page for page in inventory["pages"] if page["id"] == "inventory_risk"
    )
    risk_scatter = next(
        visual
        for visual in risk_page["visuals"]
        if visual["id"] == "risk_position_scatter"
    )
    assert risk_scatter["legend"] == "dim_warehouse.warehouse_name"
