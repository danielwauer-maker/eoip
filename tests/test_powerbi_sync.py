from __future__ import annotations

from pathlib import Path

from eoip.powerbi import parse_dax_measures, render_measure_table_tmdl


ROOT = Path(__file__).resolve().parents[1]
DAX = ROOT / "powerbi" / "measures.dax"
TMDL = (
    ROOT
    / "powerbi"
    / "EOIP"
    / "EOIP.SemanticModel"
    / "definition"
    / "tables"
    / "_Measures.tmdl"
)
MODEL = (
    ROOT
    / "powerbi"
    / "EOIP"
    / "EOIP.SemanticModel"
    / "definition"
    / "model.tmdl"
)


def test_canonical_dax_parses_to_expected_measure_set():
    measures = parse_dax_measures(DAX.read_text(encoding="utf-8"))
    names = [name for name, _expression in measures]

    assert len(measures) == 26
    assert names[:8] == [
        "Gross Sales",
        "Net Sales Base",
        "COGS",
        "Ordered Net Value",
        "Invoice Sales",
        "Credit Memo Sales",
        "Net Sales PY",
        "COGS TTM",
    ]
    assert len(names[8:]) == 18
    assert "Net Sales" in names
    assert "Gross Margin %" in names
    assert "Inventory Value" in names
    assert "Stockout-Risk SKU Count" in names


def test_committed_measure_table_is_generated_from_canonical_dax():
    measures = parse_dax_measures(DAX.read_text(encoding="utf-8"))
    expected = render_measure_table_tmdl(measures)
    actual = TMDL.read_text(encoding="utf-8")

    assert actual == expected


def test_semantic_model_references_generated_measure_table():
    model = MODEL.read_text(encoding="utf-8")
    assert "ref table _Measures" in model
