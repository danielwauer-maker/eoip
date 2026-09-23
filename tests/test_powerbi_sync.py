from __future__ import annotations

from pathlib import Path

from eoip.powerbi import (
    load_measure_metadata,
    parse_dax_measures,
    render_measure_table_tmdl,
)


ROOT = Path(__file__).resolve().parents[1]
DAX = ROOT / "powerbi" / "measures.dax"
CATALOG = ROOT / "semantic" / "kpi-catalog.yaml"
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


def test_measure_metadata_is_complete_and_governed():
    measures = parse_dax_measures(DAX.read_text(encoding="utf-8"))
    metadata = load_measure_metadata(CATALOG)

    assert set(metadata) == {name for name, _expression in measures}

    assert metadata["Gross Sales"] == {
        "format_string": "€#,##0.00",
        "display_folder": "_Helpers",
        "hidden": True,
    }
    assert metadata["Gross Margin %"] == {
        "format_string": "0.0%",
        "display_folder": "02 Margin",
        "hidden": False,
    }
    assert metadata["Inventory Turnover"] == {
        "format_string": "0.00",
        "display_folder": "03 Inventory",
        "hidden": False,
    }


def test_committed_measure_table_is_generated_from_canonical_sources():
    measures = parse_dax_measures(DAX.read_text(encoding="utf-8"))
    metadata = load_measure_metadata(CATALOG)
    expected = render_measure_table_tmdl(measures, metadata=metadata)
    actual = TMDL.read_text(encoding="utf-8")

    assert actual == expected


def test_generated_tmdl_contains_formatting_folders_and_hidden_helpers():
    text = TMDL.read_text(encoding="utf-8")

    assert "measure 'Gross Sales'" in text
    assert "formatString: €#,##0.00" in text
    assert 'displayFolder: "_Helpers"' in text
    assert "isHidden" in text

    assert "measure 'Gross Margin %'" in text
    assert "formatString: 0.0%" in text
    assert 'displayFolder: "02 Margin"' in text

    assert "measure 'Stockout-Risk SKU Count'" in text
    assert "formatString: #,##0" in text
    assert 'displayFolder: "03 Inventory"' in text


def test_semantic_model_references_generated_measure_table():
    model = MODEL.read_text(encoding="utf-8")
    assert "ref table _Measures" in model
