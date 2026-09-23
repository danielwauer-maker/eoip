from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from .semantic import load_kpi_catalog


_MEASURE_HEADER = re.compile(r"^(.+?)\s*:=\s*$")
_SIMPLE_TMDL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Stable namespace for PBIP runtime identities. UUID5 keeps lineage tags
# deterministic across machines and repeated generator runs.
_LINEAGE_NAMESPACE = uuid.UUID("0a2529a7-c2fe-5cc3-a671-10e1d261c5bd")

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


def stable_lineage_tag(identity: str) -> str:
    """Return a stable GUID for a generated PBIP semantic-model object."""
    return str(uuid.uuid5(_LINEAGE_NAMESPACE, identity))


def _tmdl_identifier(value: str) -> str:
    if _SIMPLE_TMDL_IDENTIFIER.fullmatch(value):
        return value
    return "'" + value.replace("'", "''") + "'"


def render_measure_table_tmdl(
    measures: list[tuple[str, str]],
    *,
    metadata: dict[str, dict[str, Any]] | None = None,
    table_name: str = "_Measures",
) -> str:
    """Render Power BI-normalized TMDL for the generated measure table."""
    metadata = metadata or {}
    table_identifier = _tmdl_identifier(table_name)
    lines: list[str] = [
        f"table {table_identifier}",
        f"\tlineageTag: {stable_lineage_tag(f'table:{table_name}')}",
        "",
    ]

    for name, expression in measures:
        measure_identifier = _tmdl_identifier(name)
        expression_lines = expression.splitlines()

        if len(expression_lines) == 1:
            lines.append(
                f"\tmeasure {measure_identifier} = {expression_lines[0]}"
            )
        else:
            lines.append(f"\tmeasure {measure_identifier} =")
            for expression_line in expression_lines:
                lines.append(f"\t\t\t{expression_line}")

        props = metadata.get(name, {})
        format_string = props.get("format_string")
        if format_string:
            lines.append(f"\t\tformatString: {format_string}")

        if props.get("hidden"):
            lines.append("\t\tisHidden")

        display_folder = props.get("display_folder")
        if display_folder:
            lines.append(f"\t\tdisplayFolder: {display_folder}")

        lines.append(
            f"\t\tlineageTag: {stable_lineage_tag(f'measure:{name}')}"
        )
        lines.append("")

    lines.extend(
        [
            "\tcolumn Value",
            "\t\tdataType: int64",
            "\t\tisHidden",
            "\t\tformatString: 0",
            f"\t\tlineageTag: {stable_lineage_tag(f'column:{table_name}.Value')}",
            "\t\tsummarizeBy: sum",
            "\t\tsourceColumn: [Value]",
            "",
            f"\tpartition {table_identifier} = calculated",
            "\t\tmode: import",
            "\t\tsource = {1}",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


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
