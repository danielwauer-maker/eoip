from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .semantic import load_kpi_catalog


_MEASURE_HEADER = re.compile(r"^(.+?)\s*:=\s*$")

FORMAT_STRINGS = {
    "currency_eur": "€#,##0.00",
    "percentage_1": "0.0%",
    "whole_number": "#,##0",
    "quantity": "#,##0",
    "decimal_1": "0.0",
    "decimal_2": "0.00",
}

DOMAIN_FOLDERS = {
    "sales": "01 Sales",
    "margin": "02 Margin",
    "inventory": "03 Inventory",
}


def parse_dax_measures(text: str) -> list[tuple[str, str]]:
    """Parse the canonical measures.dax file into ordered (name, expression) pairs."""
    measures: list[tuple[str, str]] = []
    current_name: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_name, current_lines
        if current_name is None:
            return
        expression = "\n".join(current_lines).strip()
        if not expression:
            raise ValueError(f"Measure {current_name!r} has no DAX expression.")
        measures.append((current_name, expression))
        current_name = None
        current_lines = []

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        match = _MEASURE_HEADER.match(stripped)
        if match:
            flush()
            current_name = match.group(1).strip()
            continue

        if current_name is None:
            continue

        if stripped.startswith("--"):
            continue
        current_lines.append(raw_line.rstrip())

    flush()

    names = [name for name, _expression in measures]
    if len(names) != len(set(names)):
        duplicates = sorted({name for name in names if names.count(name) > 1})
        raise ValueError(f"Duplicate DAX measure names: {duplicates}")

    return measures


def load_measure_metadata(catalog_path: str | Path) -> dict[str, dict[str, Any]]:
    """Build Power BI presentation metadata from the governed KPI catalog."""
    catalog = load_kpi_catalog(catalog_path)
    metadata: dict[str, dict[str, Any]] = {}

    for measure in catalog.get("base_measures", []):
        metadata[str(measure["name"])] = {
            "format_string": FORMAT_STRINGS[str(measure["format"])],
            "display_folder": str(measure.get("display_folder", "_Helpers")),
            "hidden": bool(measure.get("hidden", True)),
        }

    for kpi in catalog.get("kpis", []):
        name = str(kpi["dax"]["measure_name"])
        metadata[name] = {
            "format_string": FORMAT_STRINGS[str(kpi["format"])],
            "display_folder": DOMAIN_FOLDERS.get(
                str(kpi["domain"]),
                str(kpi["domain"]).title(),
            ),
            "hidden": False,
        }

    return metadata


def render_measure_table_tmdl(
    measures: list[tuple[str, str]],
    *,
    metadata: dict[str, dict[str, Any]] | None = None,
    table_name: str = "_Measures",
) -> str:
    """Render a measure-only calculated table for the PBIP semantic model."""
    metadata = metadata or {}
    lines: list[str] = [f"table {table_name}", ""]

    for name, expression in measures:
        safe_name = name.replace("'", "''")
        lines.append(f"\tmeasure '{safe_name}' = ```")
        for expression_line in expression.splitlines():
            lines.append(f"\t\t\t{expression_line}")
        lines.append("\t\t\t```")

        props = metadata.get(name, {})
        format_string = props.get("format_string")
        if format_string:
            lines.append(f"\t\tformatString: {format_string}")

        display_folder = props.get("display_folder")
        if display_folder:
            escaped_folder = str(display_folder).replace('"', '""')
            lines.append(f'\t\tdisplayFolder: "{escaped_folder}"')

        if props.get("hidden"):
            lines.append("\t\tisHidden")

        lines.append("")

    lines.extend(
        [
            "\tcolumn Value",
            "\t\tdataType: int64",
            "\t\tisHidden",
            "\t\tformatString: 0",
            "\t\tsummarizeBy: sum",
            "\t\tsourceColumn: [Value]",
            "",
            f"\tpartition {table_name} = calculated",
            "\t\tmode: import",
            "\t\tsource = {1}",
            "",
        ]
    )
    return "\n".join(lines)


def sync_powerbi_measures(
    dax_path: str | Path,
    tmdl_path: str | Path,
    *,
    catalog_path: str | Path = "semantic/kpi-catalog.yaml",
) -> dict[str, object]:
    dax_file = Path(dax_path)
    output_file = Path(tmdl_path)

    measures = parse_dax_measures(dax_file.read_text(encoding="utf-8"))
    metadata = load_measure_metadata(catalog_path)

    missing_metadata = sorted(name for name, _expression in measures if name not in metadata)
    if missing_metadata:
        raise ValueError(
            "Missing Power BI metadata for measures: "
            + ", ".join(missing_metadata)
        )

    rendered = render_measure_table_tmdl(measures, metadata=metadata)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(rendered, encoding="utf-8")

    return {
        "measure_count": len(measures),
        "source": str(dax_file),
        "metadata_source": str(catalog_path),
        "output": str(output_file),
    }
