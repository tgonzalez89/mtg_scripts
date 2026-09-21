from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING, Final

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt

if TYPE_CHECKING:
    from docx.table import Table, _Cell

ROWS: Final[tuple[tuple[str, str, str], ...]] = (
    ("Basic lands", "100", "20 per type"),
    ("Dual lands", "40", "10 per cycle"),
    ("Other lands", "5", ""),
    ("Colorless/Artifacts", "12", ""),
    ("Multicolor", "20", "2 per color pair"),
    ("Single color", "115", "23 per color"),
    ("Total", "192", "(non-basics)"),
    ("Players", "4", ""),
    ("Packs per player", "4", ""),
    ("Cards per booster", "12", ""),
)


def _set_cell_borders(cell: _Cell) -> None:
    """Remove visible borders from one table cell."""
    cell_properties = object.__getattribute__(cell, "_tc").get_or_add_tcPr()
    for tag in ("top", "bottom", "left", "right"):
        elements = cell_properties.xpath(f"w:tcBorders/w:{tag}")
        if elements:
            border = elements[0]
        else:
            borders = cell_properties.xpath("w:tcBorders")
            if not borders:
                borders = [OxmlElement("w:tcBorders")]
                cell_properties.append(borders[0])
            border = OxmlElement(f"w:{tag}")
            borders[0].append(border)
        border.set(qn("w:val"), "nil")
        border.set(qn("w:sz"), "0")
        border.set(qn("w:color"), "FFFFFF")


def _populate_table(table: Table) -> None:
    """Populate rows, dimensions, and border settings for the table."""
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for index, width_mm in enumerate([40, 20, 28]):
        for cell in table.columns[index].cells:
            cell.width = Mm(width_mm)
    for row in table.rows:
        row.height = Mm(63 / len(ROWS))
    for values, row in zip(ROWS, table.rows, strict=True):
        for cell, value in zip(row.cells, values, strict=True):
            cell.text = value
    for row in table.rows:
        for cell in row.cells:
            _set_cell_borders(cell)


def create_table(output_path: Path) -> None:
    """Create the MTG reference table document."""
    document = Document()
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width

    table = document.add_table(rows=len(ROWS), cols=3)
    _populate_table(table)

    document.styles["Normal"].font.size = Pt(10)
    document.save(str(output_path))
    print(f"Document saved as {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an MTG reference table document.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("mtg_table_63x88mm.docx"),
        help="Output Word document (default: mtg_table_63x88mm.docx).",
    )
    args = parser.parse_args()
    create_table(args.output)


if __name__ == "__main__":
    main()
